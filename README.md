# Enterprise Knowledge Assistant

RAG-powered search across organizational documentation. This demo uses GitLab's publicly available handbook as the knowledge base and answers questions with source passages.

## What It Does

- Loads a small curated set of GitLab handbook pages.
- Chunks text and embeds it with `sentence-transformers`.
- Stores vectors in ChromaDB.
- Retrieves top-k relevant passages for each question.
- Uses Vercel AI Gateway by default to generate grounded answers with citations.
- Shows supporting source passages.
- Falls back to an extractive answer when no hosted/local LLM is configured.
- Captures thumbs up/down feedback in `feedback.csv`.
- Tracks response latency in the UI.
- Evaluates retrieval with Recall@k on 15 manually created questions.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/ingest.py --limit 40
.venv/bin/python -m streamlit run app/streamlit_app.py
```

To generate answers with Cohere, set these values in `.env`:

```dotenv
RAG_LLM_PROVIDER=cohere
COHERE_API_KEY=your_cohere_api_key
COHERE_MODEL=command-a-plus-05-2026
COHERE_MAX_TOKENS=4096
```

Install the requirements and restart Streamlit, then select **Auto**. Retrieval
still uses the existing sentence embeddings and Chroma index. The app puts the
question and numbered retrieved passages into the user message sent to
`cohere.ClientV2.chat`, requests citations such as `[1]`, and displays the text
blocks from `response.message.content`. Missing credentials, API errors, or empty
responses show an explicit retrieval fallback with diagnostics. No index rebuild
is needed when switching the generation provider.

For deployed generation, create a Vercel AI Gateway key and set:

```bash
RAG_LLM_PROVIDER=vercel
AI_GATEWAY_API_KEY=your_vercel_ai_gateway_key
VERCEL_AI_MODEL=inclusionai/ling-3.1-flash-free
```

`VERCEL_AI_MODEL` must name a currently available gateway model. The previously
configured `inclusionai/ling-3.1-flash-free` now returns HTTP 404 because its free
tier ended. Choose a replacement and check its pricing before updating `.env`.
Set `VERCEL_AI_MAX_TOKENS=4096` (the default) to leave room for reasoning and a
final answer. In the app, select **Auto** to use the configured model. If generation
fails, the app shows a warning; enable **Show LLM diagnostics** to see the reason.

For free local generation with Ollama instead:

```bash
ollama pull llama3.2:3b
ollama serve
```

Without a hosted/local LLM, retrieval and source display still work with an extractive fallback.

Other modes:

```bash
RAG_LLM_PROVIDER=vercel       # deployed demo, requires AI_GATEWAY_API_KEY
RAG_LLM_PROVIDER=huggingface  # optional, requires HF_TOKEN and supported model
RAG_LLM_PROVIDER=ollama       # local model, requires Ollama running
RAG_LLM_PROVIDER=none         # extractive-only, no LLM
RAG_LLM_PROVIDER=openai       # optional, requires OPENAI_API_KEY
```

## Evaluate Retrieval

```bash
python scripts/evaluate.py --k 5
```

The evaluation checks whether the expected handbook page appears in the top-k retrieved sources for each question.

## Project Structure

```text
app/streamlit_app.py        Streamlit chat UI
rag/                        Loading, chunking, vector search, answer generation
scripts/ingest.py           GitLab handbook ingestion
scripts/evaluate.py         Recall@k retrieval evaluation
data/gitlab_seed_urls.txt   Curated demo corpus
data/eval/questions.csv     Manual evaluation set
```

## Deployment

For Streamlit Community Cloud:

1. Push this repo to GitHub.
2. Create a new Streamlit app from the repository.
3. Set the app entry point to `app/streamlit_app.py`.
4. Add `RAG_LLM_PROVIDER="vercel"`, `AI_GATEWAY_API_KEY`, and `VERCEL_AI_MODEL` in Streamlit secrets.
5. Open the app and use **Build demo index** in the sidebar, or run `python scripts/ingest.py --limit 40` before launching locally.

## Demo Knowledge Base

GitLab's public handbook is used only as a realistic open documentation corpus for demonstrating enterprise knowledge retrieval. Start with 30-50 pages, then expand the seed URL list as needed.

## Local Transformers imports

The Streamlit configuration disables source watching to avoid inspecting lazy
Transformers modules, which can trigger imports of optional vision packages.
Restart Streamlit after changing Python source. Retrieval uses a text embedding
model; a normal import and offline retrieval work without `torchvision` in the
project virtual environment. Launch Streamlit with that same environment using
the command above.

## Conversation context

The assistant uses the last three exchanges from the current Streamlit session to
understand follow-up questions. Short follow-ups also include recent user topics
when searching the handbook. Earlier answers are context, while the current
handbook passages supply the evidence and citation numbers. The full chat remains
visible, but only the recent window is sent with each request (up to 2,000
characters per message). **New conversation** clears the chat and its context.
This history is session-only and is not saved across browser sessions.

## General-knowledge answers

Cohere first tries the retrieved handbook evidence. If the handbook cannot answer,
it makes a separate request using the model's general knowledge; if there are no
relevant search results, it goes directly to that request. These responses are
labeled **General AI knowledge — not verified against GitLab’s handbook** and ask
readers to verify important details independently. Related handbook pages are not
presented as evidence for the general answer. This is model knowledge, not a web
search. Handbook-only excerpts remain available through the answer preferences.
A new answer automatically scrolls into view; ordinary reruns do not trigger scrolling.

## Conversation usability

- **Allow general AI knowledge** controls whether Cohere can go beyond the handbook.
- **Try again** replaces the latest answer using the same question and prior context.
- **Explain more simply** and **Show practical steps** continue the conversation.
- Numbered handbook citations open the retrieved source directly; full excerpts stay collapsed.
- **Helpful** / **Not helpful** saves one rating per answer.
- Automatic scrolling respects the system's reduced-motion setting.

These choices apply the correction, contextual suggestions, transparency, feedback,
and user-control guidance in [Microsoft's Human-AI Interaction guidelines](https://www.microsoft.com/en-us/haxtoolkit/ai-guidelines/)
and [Nielsen Norman Group's chatbot design guidance](https://www.nngroup.com/articles/ai-chatbots-design-guidelines/).
