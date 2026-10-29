from __future__ import annotations

from dataclasses import dataclass
import os
import re
import time
from typing import Optional

import requests

from rag.config import MIN_RELEVANCE_SCORE
from rag.conversation import recent_history


UNSUPPORTED = "I couldn't find this information in the indexed GitLab handbook pages."

NAVIGATION_LABELS = {
    "principles",
    "processes",
    "categories",
    "gitlab the product",
    "being a pm",
    "leadership",
    "on this page",
    "edit this page",
}

QUESTION_STOPWORDS = {
    "what",
    "which",
    "who",
    "where",
    "when",
    "why",
    "how",
    "are",
    "is",
    "the",
    "a",
    "an",
    "of",
    "for",
    "to",
    "in",
    "on",
    "and",
    "or",
    "gitlab",
    "company",
}


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    provider: str
    model: str
    used_fallback: bool
    error: Optional[str] = None
    answer_basis: str = "handbook"


def clean_passage_text(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if line.lower() in NAVIGATION_LABELS:
            continue
        if len(line.split()) <= 4 and not line.endswith((".", "?", "!")):
            continue
        lines.append(line)
    cleaned = " ".join(lines)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\.{2,}", ".", cleaned)
    return cleaned.strip()


def split_sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if len(sentence.strip().split()) >= 7
    ]


def question_terms(question: str) -> set[str]:
    terms = set()
    for token in re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", question.lower()):
        if token not in QUESTION_STOPWORDS:
            terms.add(token.rstrip("s"))
    return terms


def sentence_score(sentence: str, terms: set[str]) -> tuple[int, int]:
    normalized = sentence.lower()
    matches = sum(1 for term in terms if term in normalized)
    return matches, -len(sentence)


def build_context(passages: list[dict], max_passages: int = 4, max_chars_per_passage: int = 700) -> str:
    blocks = []
    for idx, passage in enumerate(passages[:max_passages], start=1):
        text = clean_passage_text(passage["text"])
        if len(text) > max_chars_per_passage:
            text = text[:max_chars_per_passage].rsplit(" ", 1)[0] + "..."
        blocks.append(
            f"[{idx}] Title: {passage['title']}\n"
            f"Source: {passage['source']}\n"
            f"Passage: {text}"
        )
    return "\n\n".join(blocks)


def extractive_answer(question: str, passages: list[dict]) -> str:
    if not passages or passages[0]["score"] < MIN_RELEVANCE_SCORE:
        return UNSUPPORTED

    terms = question_terms(question)
    candidates: list[tuple[tuple[int, int], int, str]] = []
    seen: set[str] = set()
    for passage_index, passage in enumerate(passages[:4]):
        for sentence in split_sentences(clean_passage_text(passage["text"])):
            normalized = sentence.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            candidates.append((sentence_score(sentence, terms), passage_index, sentence))

    if not candidates:
        return UNSUPPORTED

    ranked = sorted(candidates, key=lambda item: (item[0][0], -item[1], item[0][1]), reverse=True)
    selected_sentences = [sentence for _, _, sentence in ranked[:4]]
    bullets = "\n".join(f"- {sentence}" for sentence in selected_sentences)
    return f"Based on the retrieved handbook passages:\n\n{bullets}\n\nThe passages below show the supporting source context."


def fallback_result(question: str, passages: list[dict], provider: str, model: str = "", error: Optional[str] = None) -> AnswerResult:
    return AnswerResult(
        answer=extractive_answer(question, passages),
        provider=provider,
        model=model,
        used_fallback=True,
        error=error,
    )


def chat_completion_content(data: dict) -> str:
    message = data.get("choices", [{}])[0].get("message", {})
    content = message.get("content") or ""
    if isinstance(content, list):
        text_parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") in {"text", "output_text"}
        ]
        content = "\n".join(text_parts)
    return str(content).strip()


def post_vercel_chat(payload: dict, headers: dict) -> requests.Response:
    last_response = None
    for attempt in range(3):
        response = requests.post(
            "https://ai-gateway.vercel.sh/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=90,
        )
        last_response = response
        if response.status_code not in {429, 500, 502, 503, 504}:
            return response
        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))
    return last_response


def build_prompt(question: str, passages: list[dict], history: list[dict] | None = None) -> str:
    conversation = "\n".join(
        f"{message['role'].capitalize()}: {message['content']}"
        for message in recent_history(history)
    ) or "No previous messages."
    return f"""
Answer the user's question using only the provided GitLab handbook passages.
If the passages do not contain enough information, say exactly:
"{UNSUPPORTED}"

Requirements:
- Be concise and practical.
- Do not use outside knowledge.
- Use recent conversation only to understand follow-up questions and references.
- Earlier assistant answers are not evidence. Ground facts and citations in the current passages.
- Citation numbers refer only to the current passages, not earlier answers.
- Cite supporting passages inline with bracket numbers, such as [1] or [2].
- Return only the final answer. Do not include analysis, reasoning, or planning text.

Recent conversation (context only):
{conversation}

Current question: {question}

Passages:
{build_context(passages)}
"""


def generate_ollama_answer(question: str, passages: list[dict], history: list[dict] | None = None) -> str:
    model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    payload = {
        "model": model,
        "prompt": build_prompt(question, passages, history),
        "stream": False,
        "options": {"temperature": 0.1},
    }
    try:
        response = requests.post(f"{base_url}/api/generate", json=payload, timeout=90)
        response.raise_for_status()
    except requests.RequestException:
        return extractive_answer(question, passages)
    return response.json().get("response") or extractive_answer(question, passages)


def generate_openai_answer(question: str, passages: list[dict], history: list[dict] | None = None) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return extractive_answer(question, passages)

    try:
        from openai import OpenAI
    except ModuleNotFoundError:
        return extractive_answer(question, passages)

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": "You are a grounded enterprise knowledge assistant."},
            {"role": "user", "content": build_prompt(question, passages, history)},
        ],
        temperature=0.1,
    )
    return response.choices[0].message.content or UNSUPPORTED


def generate_huggingface_answer(question: str, passages: list[dict], history: list[dict] | None = None) -> str:
    token = os.getenv("HF_TOKEN")
    if not token:
        return extractive_answer(question, passages)

    model = os.getenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.3")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a grounded enterprise knowledge assistant."},
            {"role": "user", "content": build_prompt(question, passages, history)},
        ],
        "temperature": 0.1,
        "max_tokens": 450,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            "https://router.huggingface.co/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=90,
        )
        response.raise_for_status()
    except requests.RequestException:
        return extractive_answer(question, passages)

    data = response.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content") or extractive_answer(question, passages)


def generate_vercel_answer(question: str, passages: list[dict], history: list[dict] | None = None) -> str:
    return generate_vercel_result(question, passages, history).answer


def generate_vercel_result(question: str, passages: list[dict], history: list[dict] | None = None) -> AnswerResult:
    api_key = os.getenv("AI_GATEWAY_API_KEY")
    model = os.getenv("VERCEL_AI_MODEL", "inclusionai/ling-3.1-flash-free")
    if not api_key:
        return fallback_result(question, passages, provider="vercel", model=model, error="Missing AI_GATEWAY_API_KEY.")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a grounded enterprise knowledge assistant."},
            {"role": "user", "content": build_prompt(question, passages, history)},
        ],
        "temperature": 0.1,
        "max_tokens": int(os.getenv("VERCEL_AI_MAX_TOKENS", "4096")),
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = post_vercel_chat(payload, headers)
        response.raise_for_status()
        data = response.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        return fallback_result(
            question,
            passages,
            provider="vercel",
            model=model,
            error=f"Vercel AI Gateway HTTP {status}: {detail}",
        )
    except requests.RequestException as exc:
        return fallback_result(question, passages, provider="vercel", model=model, error=f"Vercel request failed: {exc}")
    except ValueError as exc:
        return fallback_result(question, passages, provider="vercel", model=model, error=f"Vercel returned invalid JSON: {exc}")

    answer = chat_completion_content(data)
    if not answer:
        return fallback_result(
            question, passages, provider="vercel", model=model,
            error=(
                "Vercel returned no final answer "
                f"(finish_reason={data.get('choices', [{}])[0].get('finish_reason')}, "
                f"usage={data.get('usage', {})}). "
                "If finish_reason is length, increase VERCEL_AI_MAX_TOKENS; "
                "the model may have used its budget for reasoning."
            ),
        )

    return AnswerResult(answer=answer, provider="vercel", model=model, used_fallback=False)


def is_unsupported_answer(answer: str) -> bool:
    normalized = answer.lower().replace("’", "'").strip(' \n"')
    return normalized.startswith(UNSUPPORTED.lower()) or bool(re.match(
        r"(?:i\s+)?(?:couldn't|could not|can't|cannot|couldnt) find "
        r"(?:the answer|an answer|this information).*"
        r"(?:passages|handbook|knowledge base|sources|documents)",
        normalized, flags=re.DOTALL,
    ))


def add_closest_matches(answer: str, passages: list[dict]) -> str:
    if not is_unsupported_answer(answer):
        return answer

    links = []
    seen = set()
    # Use only passages the model saw, preserving retrieval order.
    for passage in passages[:4]:
        source = passage.get("source", "")
        if (not source or source in seen
                or passage.get("score", 0) < MIN_RELEVANCE_SCORE):
            continue
        seen.add(source)
        title = passage.get("title") or "Handbook page"
        title = title.replace("[", r"\[").replace("]", r"\]")
        links.append(f"- [{title}](<{source}>)")
        if len(links) == 3:
            break

    if not links:
        return answer + (
            "\n\nPlease rephrase your question or expand the knowledge base using "
            "**Manage knowledge base → Handbook pages to include → Update knowledge base**."
        )
    return answer + (
        "\n\n**Closest matches**\n\n"
        "Your topic may be mentioned in these pages, but the retrieved information "
        "does not directly answer your question:\n\n"
        + "\n".join(links)
        + "\n\nPlease rephrase your question or expand the knowledge base using "
        "**Manage knowledge base → Handbook pages to include → Update knowledge base**."
    )


def generate_cohere_result(question: str, passages: list[dict], history: list[dict] | None = None, allow_general_knowledge: bool = True) -> AnswerResult:
    model = os.getenv("COHERE_MODEL", "command-a-plus-05-2026")
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        return fallback_result(question, passages, provider="cohere", model=model,
                               error="Missing COHERE_API_KEY.")
    try:
        import cohere
        from cohere.core.api_error import ApiError
        from httpx import HTTPError
    except ImportError:
        return fallback_result(question, passages, provider="cohere", model=model,
                               error="Cohere SDK is missing. Run python -m pip install -r requirements.txt.")

    answer_basis = "handbook"
    has_evidence = bool(passages and passages[0]["score"] >= MIN_RELEVANCE_SCORE)

    def response_text(response) -> str:
        return "\n".join(
            part.text for part in (response.message.content or [])
            if part.type == "text" and part.text
        ).strip()

    try:
        with cohere.ClientV2(api_key=api_key, timeout=90) as client:
            answer = ""
            if has_evidence:
                response = client.chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a grounded enterprise knowledge assistant."},
                        {"role": "user", "content": build_prompt(question, passages, history)},
                    ],
                    temperature=0.1,
                    max_tokens=int(os.getenv("COHERE_MAX_TOKENS", "4096")),
                )
                answer = response_text(response)
                if not answer:
                    return fallback_result(
                        question, passages, provider="cohere", model=model,
                        error=f"Cohere returned no final text (finish_reason={response.finish_reason}).",
                    )
            if not has_evidence or is_unsupported_answer(answer):
                if not allow_general_knowledge:
                    return AnswerResult(
                        answer=add_closest_matches(UNSUPPORTED, passages), provider="cohere",
                        model=model, used_fallback=False,
                    )
                answer_basis = "general_knowledge"
                response = client.chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": (
                            "The indexed GitLab handbook did not answer the current question. "
                            "You may answer from your general knowledge. Be concise and acknowledge uncertainty. "
                            "Do not invent GitLab policies, internal facts, source links, or citations. "
                            "If the question requires GitLab-specific information, say you cannot confirm it "
                            "and distinguish any general guidance from GitLab policy. "
                            "You have not searched the web. Do not claim this answer is verified or current. "
                            "Use earlier messages only as conversational context, not verified facts."
                        )},
                        *recent_history(history),
                        {"role": "user", "content": question},
                    ],
                    temperature=0.1,
                    max_tokens=int(os.getenv("COHERE_MAX_TOKENS", "4096")),
                )
                answer = response_text(response)
                if not answer:
                    return fallback_result(
                        question, passages, provider="cohere", model=model,
                        error="Cohere returned no general-knowledge answer.",
                    )
    except ApiError as exc:
        return fallback_result(question, passages, provider="cohere", model=model,
                               error=f"Cohere API HTTP {exc.status_code}: {str(exc.body)[:500]}")
    except HTTPError:
        return fallback_result(question, passages, provider="cohere", model=model,
                               error="Cohere request failed. Check your connection or try again.")
    except ValueError:
        return fallback_result(question, passages, provider="cohere", model=model,
                               error="Invalid Cohere configuration or response. COHERE_MAX_TOKENS must be an integer.")

    if answer_basis == "general_knowledge":
        answer = (
            "**General AI knowledge — not verified against GitLab’s handbook.**"
            "\n\n" + answer
            + "\n\nVerify important details with reliable sources; you can also rephrase your question or expand the knowledge base."
        )
    return AnswerResult(answer=answer, provider="cohere", model=model,
                        used_fallback=False, answer_basis=answer_basis)


def generate_answer(question: str, passages: list[dict], history: list[dict] | None = None) -> str:
    provider = os.getenv("RAG_LLM_PROVIDER", "vercel").lower()
    if provider == "cohere":
        return generate_cohere_result(question, passages, history).answer

    if not passages or passages[0]["score"] < MIN_RELEVANCE_SCORE:
        return UNSUPPORTED

    if provider == "vercel":
        return generate_vercel_answer(question, passages, history)
    if provider == "huggingface":
        return generate_huggingface_answer(question, passages, history)
    if provider == "openai":
        return generate_openai_answer(question, passages, history)
    if provider == "none":
        return extractive_answer(question, passages)
    return generate_ollama_answer(question, passages, history)


def generate_answer_with_metadata(question: str, passages: list[dict], history: list[dict] | None = None, allow_general_knowledge: bool = True) -> AnswerResult:
    provider = os.getenv("RAG_LLM_PROVIDER", "vercel").lower()
    if provider == "cohere":
        return generate_cohere_result(question, passages, history, allow_general_knowledge)

    if not passages or passages[0]["score"] < MIN_RELEVANCE_SCORE:
        return AnswerResult(
            answer=UNSUPPORTED,
            provider=os.getenv("RAG_LLM_PROVIDER", "vercel").lower(),
            model="",
            used_fallback=True,
            error="No retrieved passage met the minimum relevance threshold.",
        )

    if provider == "vercel":
        return generate_vercel_result(question, passages, history)
    if provider == "none":
        return fallback_result(question, passages, provider="none")

    answer = generate_answer(question, passages, history)
    return AnswerResult(
        answer=answer,
        provider=provider,
        model=os.getenv(f"{provider.upper()}_MODEL", ""),
        used_fallback=answer.startswith("Here is what the indexed handbook passages say:"),
    )


def generate_retrieval_answer(question: str, passages: list[dict]) -> AnswerResult:
    if not passages or passages[0]["score"] < MIN_RELEVANCE_SCORE:
        return AnswerResult(
            answer=UNSUPPORTED,
            provider="none",
            model="",
            used_fallback=True,
            error="No retrieved passage met the minimum relevance threshold.",
        )
    return fallback_result(question, passages, provider="none")
