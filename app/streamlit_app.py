from __future__ import annotations

import csv
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from rag.bootstrap import ensure_knowledge_base
from rag.demo import admit_question, demo_mode, question_limit
from rag.conversation import recent_history, retrieval_question
from rag.chunking import chunk_documents
from rag.config import DEFAULT_TOP_K, FEEDBACK_PATH, SEED_URLS_PATH
from rag.loaders import HandbookLoadError, load_url, read_seed_urls
from rag.llm import generate_answer_with_metadata, generate_retrieval_answer

try:
    from rag.vector_store import get_collection, index_chunks, retrieve
except ModuleNotFoundError as exc:
    st.error(f"Missing Python package: `{exc.name}`")
    st.code("pip install -r requirements.txt", language="bash")
    st.stop()


load_dotenv()
st.set_page_config(page_title="EKassistant", page_icon="📖", layout="wide")
st.markdown((ROOT_DIR / "app" / "assets" / "styles.css").read_text(), unsafe_allow_html=True)


DEMO_MODE = demo_mode()


@st.cache_resource(show_spinner=False)
def initialize_knowledge_base():
    return ensure_knowledge_base()


with st.spinner("Getting the handbook ready…"):
    try:
        ready_sections = initialize_knowledge_base()
    except Exception:
        st.error("The handbook is temporarily unavailable. Please try loading the app again shortly.")
        st.stop()


def scroll_to_answer(answer_id: str) -> None:
    # Run only after a new answer; normal reruns preserve the reader's position.
    components.html(
        f"""<script>
        const doc = window.parent.document;
        const scroll = () => {{
            const anchor = doc.getElementById("{answer_id}");
            if (anchor) {{
                const message = anchor.closest('[data-testid="stChatMessage"]') || anchor;
                message.scrollIntoView({{behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start"}});
                return true;
            }}
            return false;
        }};
        if (!scroll()) {{
            const observer = new MutationObserver(() => {{ if (scroll()) observer.disconnect(); }});
            observer.observe(doc.body, {{childList: true, subtree: true}});
            setTimeout(() => observer.disconnect(), 5000);
        }}
        </script>""",
        height=0,
    )


def record_feedback(question: str, answer: str, rating: str, latency_ms: int) -> None:
    if DEMO_MODE:
        return
    exists = FEEDBACK_PATH.exists()
    with FEEDBACK_PATH.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "question", "answer", "rating", "latency_ms"],
        )
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "question": question,
                "answer": answer,
                "rating": rating,
                "latency_ms": latency_ms,
            }
        )


def collection_count() -> int:
    return get_collection().count()


def build_demo_index(limit: int) -> tuple[int, list[str]]:
    documents = []
    skipped = []
    for url in read_seed_urls(SEED_URLS_PATH)[:limit]:
        try:
            doc = load_url(url)
        except HandbookLoadError as exc:
            skipped.append(str(exc))
            continue
        if len(doc.text) > 500:
            documents.append(doc)
    chunks = chunk_documents(documents)
    return index_chunks(chunks, reset=True), skipped


st.markdown('<div class="eyebrow">YOUR HANDBOOK, CONNECTED</div>', unsafe_allow_html=True)
st.title("EKassistant")
st.markdown(
    '<p class="welcome">Hi, I’m here to help you find answers in GitLab’s handbook, '
    'understand company processes, and explore related topics. I’ll clearly label '
    'handbook answers and general AI guidance.</p>', unsafe_allow_html=True,
)
st.markdown(
    '<div class="context-tags"><span>GitLab public handbook</span>'
    '<span>Answers with sources</span><span>Follow-up questions welcome</span></div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown(
        '<div class="sidebar-brand"><div class="brand-mark">EK</div>'
        '<div class="brand-name">EKassistant<small>GitLab handbook workspace</small></div></div>',
        unsafe_allow_html=True,
    )
    if st.button("New conversation", type="primary", use_container_width=True):
        st.session_state.messages = []
        st.session_state.pop("pending_question", None)
        st.session_state.pop("pending_retry", None)
        for feedback_key in list(st.session_state):
            if feedback_key.startswith("feedback-"):
                del st.session_state[feedback_key]
        st.rerun()
    st.caption("Remembers the last 3 exchanges in this session.")
    if DEMO_MODE:
        remaining = max(0, question_limit() - st.session_state.get("demo_questions", 0))
        quota_status = st.empty()
        quota_status.caption(f"Public demo · {remaining} questions remaining")
        st.caption("Chat stays in this session; feedback storage is off. Questions are sent to the configured AI service.")
    st.divider()
    st.header("Answer preferences")
    top_k = st.slider(
        "Search coverage", min_value=2, max_value=8, value=DEFAULT_TOP_K,
        help="How many handbook sections to review for each answer. Increase this to consider more supporting information.",
    )
    answer_mode = st.radio(
        "Answer style",
        options=["Summarized answer", "Handbook excerpts"],
        help="Summarized answer uses AI to explain handbook information. Cohere can also offer clearly labeled general guidance when the handbook cannot answer. Handbook excerpts shows selected sentences from the handbook.",
    )
    allow_general_knowledge = st.toggle(
        "Allow general AI knowledge", value=True,
        disabled=answer_mode == "Handbook excerpts",
        help="For Cohere summaries: allow general guidance when the handbook cannot answer. Turn off for handbook-only answers.",
    )
    debug_llm = False
    if not DEMO_MODE:
        st.divider()
        with st.expander("Manage knowledge base"):
            st.caption("Choose how many handbook pages to make available for answering questions. Updating replaces the current collection.")
            st.metric("Searchable handbook sections", collection_count())
            build_limit = st.slider("Handbook pages to include", min_value=10, max_value=50, value=30)
            if st.button("Update knowledge base", use_container_width=True):
                with st.spinner("Preparing handbook pages for search..."):
                    count, skipped = build_demo_index(build_limit)
                st.session_state.index_status = {"count": count, "skipped": skipped}
                st.rerun()
            if "index_status" in st.session_state:
                status = st.session_state.index_status
                st.success(f"Knowledge base ready: {status['count']} searchable sections.")
                if status["skipped"]:
                    with st.expander(f"Skipped {len(status['skipped'])} unavailable pages"):
                        for item in status["skipped"]:
                            st.write(item)
        with st.expander("Technical details"):
            debug_llm = st.checkbox("Show connection diagnostics", value=False)
            provider = os.getenv("RAG_LLM_PROVIDER", "vercel")
            default_model = "command-a-plus-05-2026" if provider == "cohere" else ""
            model = os.getenv(f"{provider.upper()}_MODEL", default_model)
            key_name = {"cohere": "COHERE_API_KEY", "vercel": "AI_GATEWAY_API_KEY",
                        "openai": "OPENAI_API_KEY", "huggingface": "HF_TOKEN"}.get(provider)
            has_key = bool(os.getenv(key_name)) if key_name else False
            st.write(f"Provider: `{provider}`")
            if model:
                st.write(f"Model: `{model}`")
            if key_name:
                st.write(f"{key_name} loaded: `{'yes' if has_key else 'no'}`")

if "messages" not in st.session_state:
    st.session_state.messages = []

examples = [
    ("Product strategy", "Principles that guide product decisions.", "What is the importance of GitLab's product principles?"),
    ("Working together", "How teams communicate across time zones.", "How does GitLab approach asynchronous communication?"),
    ("Customer support", "Understand the team’s role and responsibilities.", "What are Customer Support responsibilities?"),
]

if not st.session_state.messages:
    st.markdown('<p class="section-label">A few places to start</p>', unsafe_allow_html=True)
    cols = st.columns(len(examples), gap="medium")
    for col, (topic, description, example) in zip(cols, examples):
        with col, st.container(border=True):
            st.markdown(f"**{topic}**")
            st.caption(description)
            if st.button(example, use_container_width=True):
                st.session_state.pending_question = example
    st.caption("Ask a question below, then keep the conversation going with a follow-up.")
else:
    st.markdown('<p class="section-label">Your conversation</p>', unsafe_allow_html=True)

def queue_follow_up(question: str) -> None:
    st.session_state.pending_question = question


def retry_last_answer(message_index: int, question: str) -> None:
    st.session_state.pending_retry = message_index
    st.session_state.pending_question = question


def cited_answer(message: dict) -> str:
    if message.get("llm", {}).get("answer_basis") == "general_knowledge":
        return message["content"]
    sources = message.get("sources", [])[:4]

    def link(match):
        number = int(match.group(1))
        if 1 <= number <= len(sources):
            url = sources[number - 1].get("source", "")
            if url.startswith(("https://", "http://")):
                url = url.replace(">", "%3E").replace("<", "%3C")
                return f"[{number}](<{url}>)"
        return match.group(0)

    return re.sub(r"(?<!!)\[(\d+)\](?!\()", link, message["content"])


def render_answer(message: dict, message_index: int) -> None:
    st.markdown(cited_answer(message))
    llm = message.get("llm", {})
    general = llm.get("answer_basis") == "general_knowledge"
    status = "General AI knowledge" if general else (
        "Handbook excerpts" if llm.get("used_fallback") else "Handbook answer"
    )
    st.caption(f"{status} · {message['latency_ms'] / 1000:.1f}s")
    if llm.get("error"):
        st.warning("A summary is unavailable. Try again or rephrase your question.")
    if debug_llm:
        st.caption(f"{llm.get('provider', '')} · {llm.get('model', '')}")
        if llm.get("error"):
            with st.expander("Connection diagnostic"):
                st.code(llm["error"])
    if message["sources"]:
        label = "Related handbook pages" if general else "Sources and passages"
        with st.expander(label, expanded=False):
            for idx, source in enumerate(message["sources"], start=1):
                st.markdown(f"**[{idx}] [{source['title']}]({source['source']})**")
                st.write(source["text"][:900])
    actions = st.columns([1.3, 1.5, 1.4, 3], gap="small")
    if not DEMO_MODE:
        vote_key = f"feedback-{message_index}-{message['latency_ms']}"
        voted = vote_key in st.session_state
        for col, label, rating in [(actions[0], "Helpful", "up"), (actions[1], "Not helpful", "down")]:
            if col.button(label, key=f"{rating}-{vote_key}", disabled=voted):
                record_feedback(message["question"], message["content"], rating, message["latency_ms"])
                st.session_state[vote_key] = rating
                st.toast("Thanks for your feedback.")
                st.rerun()
    if message_index == len(st.session_state.messages) - 1:
        actions[2].button(
            "Try again", key=f"retry-{message_index}",
            on_click=retry_last_answer, args=(message_index, message["question"]),
        )
        if not llm.get("error"):
            with st.container(key=f"next_steps_{message_index}"):
                st.markdown('<p class="next-steps-label">Continue the conversation</p>', unsafe_allow_html=True)
                follow_ups = st.columns(2, gap="small")
                for col, label, icon, question in [
                    (follow_ups[0], "Explain more simply", ":material/short_text:",
                     "Can you explain your last answer more simply?"),
                    (follow_ups[1], "Show practical steps", ":material/checklist:",
                     "Based on that, what practical steps can I take?"),
                ]:
                    col.button(
                        label, icon=icon, key=f"follow-{label}-{message_index}",
                        use_container_width=True, on_click=queue_follow_up, args=(question,),
                    )


for message_index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message["role"] == "assistant" and "sources" in message:
            render_answer(message, message_index)
        else:
            st.markdown(message["content"])

question = st.chat_input("Ask a question about the handbook…")
if "pending_question" in st.session_state:
    question = st.session_state.pop("pending_question")

if question:
    denial = admit_question(st.session_state)
    if denial:
        st.session_state.pop("pending_retry", None)
        st.info(denial)
        st.stop()
    if DEMO_MODE:
        remaining = max(0, question_limit() - st.session_state.get("demo_questions", 0))
        quota_status.caption(f"Public demo · {remaining} questions remaining")
    retry_index = st.session_state.pop("pending_retry", None)
    if retry_index is not None:
        st.session_state.messages = st.session_state.messages[:retry_index - 1]
    history = recent_history(st.session_state.messages)
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    answer_id = f"answer-{len(st.session_state.messages)}"
    with st.container():
        start = time.perf_counter()
        with st.spinner("Searching the handbook..."):
            sources = retrieve(retrieval_question(question, history), top_k=top_k)
            if answer_mode == "Handbook excerpts":
                answer_result = generate_retrieval_answer(question, sources)
            else:
                answer_result = generate_answer_with_metadata(question, sources, history=history, allow_general_knowledge=allow_general_knowledge)
            answer = answer_result.answer
        latency_ms = int((time.perf_counter() - start) * 1000)
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer,
            "sources": sources,
            "latency_ms": latency_ms,
            "question": question,
            "llm": {
                "provider": answer_result.provider,
                "model": answer_result.model,
                "used_fallback": answer_result.used_fallback,
                "error": answer_result.error,
                "answer_basis": answer_result.answer_basis,
            },
        }
    )

    with st.chat_message("assistant"):
        st.markdown(f'<div id="{answer_id}-ready" class="answer-anchor"></div>', unsafe_allow_html=True)
        render_answer(st.session_state.messages[-1], len(st.session_state.messages) - 1)
    scroll_to_answer(f"{answer_id}-ready")
