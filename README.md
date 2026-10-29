# EKassistant

**Your shortcut to answers in the company handbook.**

EKassistant is an enterprise knowledge assistant that helps people find information, understand company processes, and turn guidance into practical next steps—without searching through pages of documentation.

This demo uses selected pages from **GitLab’s public handbook**. Ask a question in everyday language, read a clear answer, and open the original sources to learn more.

## See it in action

![24-second EKassistant walkthrough: ask a handbook question, inspect sources, and ask a simpler follow-up.](docs/ekassistant-demo.gif)

*A 24-second recording of the app: a real Cohere answer, handbook sources, and a conversational follow-up.*

## Try the live app

**[Open EKassistant →](https://ekassistant-ma9ahil.streamlit.app/)**

The app is hosted on Streamlit. You can try it in your browser without installing anything.

## Core features

| Feature | What it does |
| --- | --- |
| **Handbook answers** | Finds relevant GitLab information and summarizes it, or shows handbook excerpts. |
| **Verifiable sources** | Click numbered citations; expand the original passages when needed. |
| **Conversation context** | Uses the last three exchanges to understand follow-up questions. |
| **Labeled general guidance** | Optional Cohere fallback, clearly distinguished from handbook information. |
| **Ready on first visit** | Restores bundled search data automatically after a restart. |
| **Protected public demo** | Session limits, a shared AI-call cap, hidden management controls, and no feedback-file collection. |

## Retrieval evaluation

Measured on **25 manually labeled questions**, against the shipped snapshot of **970 sections from 23 pages**, using a fresh temporary Chroma database. No Cohere calls are involved.

| Retrieval strategy | Hit@5 | MRR@5 |
| --- | ---: | ---: |
| Before: similarity ranking | **76.0% (19/25)** | **0.6200** |
| After: one best section per source page | **76.0% (19/25)** | **0.6233** |

**Hit@5** asks whether the reference page appears among the first five results. **MRR@5** rewards finding it earlier, with zero credit for a miss. Both strategies use the same 25 nearest candidate sections, embedding model, corpus, and question labels; only selection of the final five changes.

The source-diversity experiment improves the security-handbook question from rank **4 → 3**. The overall gain is small (**+0.0033 MRR**, no hit-rate gain), so similarity ranking remains the default: limiting every page to one section could discard useful detail. Set `RAG_RETRIEVAL_STRATEGY=source_diversity` to try the alternative.

All six misses reference pages absent from this snapshot. On the 19 questions whose reference pages are present, both strategies achieve **100% Hit@5**; MRR@5 is **0.8158 → 0.8202**. The full-set score above keeps these missing-page cases in the denominator. Expanding corpus coverage is the clearest next step.

These are development-set retrieval results, not a held-out benchmark or a measure of answer correctness. Each question has one reference URL; another page may also answer it. The generation prompt currently includes only the first four results; Hit@4 is also **76%** for both strategies. See the [question set](data/eval/questions.csv), [per-question results and input hashes](data/eval/results.json), and [evaluation methodology](data/eval/README.md).

Reproduce the comparison without changing the app’s database:

```bash
python scripts/evaluate.py --k 5 --strategy compare --output data/eval/results.json
```

## Architecture

```mermaid
flowchart LR
    A[Public GitLab pages] --> B[Ingest]
    B --> C[Chunk: 1100 characters<br/>180-character overlap]
    C --> D[Embed: MiniLM<br/>384 dimensions]
    D --> E[(Chroma)]
    E --> F[Retrieve and select]
    Q[Question + recent context] --> F
    F --> G[Prompt: up to 4 cited passages]
    G --> H[Cohere]
    H --> I[Cited handbook answer]
    H -. Handbook cannot answer .-> J[Optional general-knowledge request]
    J --> K[Labeled general guidance]
```

| Decision | Rationale and tradeoff |
| --- | --- |
| **1,100-character sections, 180-character overlap** | A practical starting point for short, locally searchable excerpts; overlap preserves some context at boundaries. Paragraphs are kept together when possible. These values have not been optimized in a chunk-size ablation. |
| **`all-MiniLM-L6-v2` embeddings** | A compact model that runs locally on CPU, avoiding a paid embedding API. Its [model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) documents 384-dimensional vectors and a 256-word-piece input limit; character-based chunks can still exceed that limit and be truncated. |
| **Chroma with cosine distance** | A local vector database keeps the demo simple. A portable snapshot supplies precomputed document vectors; queries use the same embedding model. The evaluator restores that exact snapshot into an isolated database. |
| **Small, explicit generation context** | The prompt includes up to four passages, capped at 700 characters each, plus the last three exchanges. This bounds request size, but may omit useful evidence. Earlier answers are context, not sources. |
| **Separate general-knowledge fallback** | Cohere first tries the handbook. If it cannot answer, an optional second request produces labeled general guidance without treating handbook links as supporting evidence. |

The chunk size, passage limits, and relevance threshold are demo heuristics, not validated production settings. The current evaluation covers page retrieval; groundedness, citation accuracy, and multi-turn answer quality still need a separate evaluation.

## Getting started

1. Open [EKassistant](https://ekassistant-ma9ahil.streamlit.app/).
2. Pick a suggested topic or type your own question.
3. Read the answer and open its source links if you want to check the details.
4. Ask a follow-up or choose one of the next-step buttons.

A few questions to try:

- “What are GitLab’s product principles?”
- “How does GitLab approach asynchronous communication?”
- “What are Customer Support responsibilities?”
- Follow up with “Can you explain that more simply?”

The public demo prepares the handbook automatically. There is no setup button to click. Each session allows five questions, including retries and follow-ups, with at least ten seconds between requests. **New conversation** clears the chat without resetting that allowance.

## Make the answers work for you

Under **Answer preferences**:

- **Search coverage** controls how many handbook sections are searched for each question.
- **Answer style** switches between an AI summary and selected handbook sentences.
- **Allow general AI knowledge** lets Cohere offer broader guidance when the handbook does not answer. Switch it off if you only want handbook information.

Knowledge-base management is available only when the owner starts the app with `DEMO_MODE=false`; it is hidden in the public demo.

## Understanding the answers

**Handbook answers** use the information found in the selected GitLab pages and include numbered citations.

**General AI knowledge** comes from the model’s learned knowledge, rather than verified handbook information or a live web search. It is labeled separately and may be inaccurate or out of date.

This is a demonstration using a selection of public pages, not GitLab’s official assistant or a complete copy of its handbook.

## Conversation history and feedback

The conversation remains visible during your session, but only the last three exchanges are used to understand follow-ups. History is not saved as a permanent chat archive. Select **New conversation** to start fresh.

The public demo disables feedback collection and does not write questions or answers to a feedback file. Chat messages are held in session memory. For AI-generated answers, your question and recent context are sent to Cohere; provider-side retention is governed by its terms.

In local development mode (`DEMO_MODE=false`), **Helpful / Not helpful** feedback writes the timestamp, question, answer, rating, and response time to `feedback.csv`. This file is ignored by Git and is not a durable storage service on Streamlit Cloud.

<details>
<summary>More interaction features</summary>

- **Explain more simply** and **Show practical steps** continue the conversation.
- **Try again** replaces the latest answer without retyping the question.
- **Search coverage** changes how many results are selected for an answer.
- **Closest matches** suggests related pages when handbook-only answers cannot resolve a question.
- **New conversation** clears chat context, while preserving demo usage counts.
- New answers scroll into view, respecting reduced-motion preferences.
- Answer labels and response times remain visible; technical diagnostics stay hidden in the public demo.
- Local development mode supports one **Helpful / Not helpful** rating per answer and knowledge-base management.

</details>

## Run your own copy

The live app is the easiest way to try EKassistant. The instructions below are for someone setting up their own copy on a computer.

### 1. Install the app

Open a terminal in the downloaded project folder:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.

### 2. Connect Cohere

A Cohere API key connects the app to the service that writes AI answers. Add these settings to your local `.env` file:

```dotenv
RAG_LLM_PROVIDER=cohere
COHERE_API_KEY=your_cohere_api_key
COHERE_MODEL=command-a-plus-05-2026
COHERE_MAX_TOKENS=4096
```

### 3. Start the app

```bash
python -m streamlit run app/streamlit_app.py
```

Open the local address shown in the terminal. The included snapshot restores the handbook automatically. To enable owner controls and local feedback collection, set `DEMO_MODE=false` in your local `.env` and restart.

Restart the app after changing its Python code; automatic code watching is disabled in this project.

## Deploy your own app

The existing deployment is available at **[ekassistant-ma9ahil.streamlit.app](https://ekassistant-ma9ahil.streamlit.app/)**.

To publish your own copy on Streamlit Community Cloud:

1. Put the project in a GitHub repository.
2. Create a Streamlit app connected to that repository.
3. Set the app’s main file to `app/streamlit_app.py`.
4. Add the following in the app’s **Secrets** settings, replacing the API key placeholder:

   ```toml
   RAG_LLM_PROVIDER = "cohere"
   COHERE_API_KEY = "your_cohere_api_key"
   COHERE_MODEL = "command-a-plus-05-2026"
   COHERE_MAX_TOKENS = 4096
   DEMO_MODE = true
   DEMO_SESSION_QUESTIONS = 5
   DEMO_COOLDOWN_SECONDS = 10
   DEMO_SERVER_API_CALLS = 50
   ```

5. Deploy and open the app in a private/incognito window. The handbook should initialize automatically, without management controls or feedback buttons.

Keep real API keys in local `.env` or Streamlit Secrets, rather than in the README or committed code. After a restart, the app restores its local search database from `data/demo/handbook.json.gz`. This portable snapshot contains 970 sections from seed-listed public GitLab pages and their precomputed search vectors. Startup makes no Cohere requests and does not scrape handbook pages; the text-embedding model may still need an initial download.

### Demo limits

`DEMO_MODE=true` is the default, including when the setting is absent. Do not set it to false on the public deployment: it is a deployment setting, not an authenticated admin login.

The public demo allows five questions per browser session, including retries and follow-ups, and a ten-second cooldown. A shared cap allows at most 50 Cohere requests per server process; a general-knowledge fallback can use a second request. Automatic Cohere retries are disabled. These are lightweight demo controls: a fresh browser session resets the session allowance, and a server restart resets the shared counter. They do **not** enforce a durable monthly quota. Set a provider-side usage limit as well where available.

### Refresh the bundled handbook

From a trusted local environment, load the latest public pages and export a replacement snapshot:

```bash
python -m scripts.ingest --limit 40
python scripts/export_demo_snapshot.py
```

Commit `data/demo/handbook.json.gz` along with the code. The export accepts only URLs listed in `data/gitlab_seed_urls.txt`; private/local documents are excluded. Snapshot content is a point-in-time copy, not a live handbook feed. Original page URLs are preserved for attribution and verification.

## For developers

EKassistant uses Streamlit for the interface, sentence-transformers to find related text, and ChromaDB to store searchable handbook sections. Cohere generates the answers in the configuration above. The code also supports Vercel AI Gateway, OpenAI, Hugging Face, Ollama, and a handbook-excerpts-only mode (`RAG_LLM_PROVIDER=none`). Other providers have their own configuration; general-knowledge fallback is implemented for Cohere.

| Location | Purpose |
| --- | --- |
| `app/streamlit_app.py` | Chat interface and user controls. |
| `app/assets/styles.css` | Visual styling. |
| `rag/` | Loads handbook pages, searches them, manages conversation context, and generates answers. |
| `data/gitlab_seed_urls.txt` | The list of handbook pages available to load. Add URLs here to extend the demo collection. |
| `data/demo/handbook.json.gz` | Bundled public search data restored automatically at startup. |
| `rag/demo.py` | Public demo session limits and shared AI-call budget. |
| `scripts/export_demo_snapshot.py` | Exports a portable snapshot of seed-listed public pages. |
| `scripts/ingest.py` | Prepares handbook pages for search from the command line. |
| `scripts/evaluate.py` | Checks whether searches find the expected handbook pages. |
| `tests/` | Automated checks for answer generation and conversation behavior. |

Run the checks:

```bash
python -m unittest discover -s tests -v
```

Evaluate retrieval against the bundled snapshot (no separate ingestion required):

```bash
python scripts/evaluate.py --k 5 --strategy compare --output data/eval/results.json
```

The interface draws on [Microsoft’s Human-AI Interaction guidelines](https://www.microsoft.com/en-us/haxtoolkit/ai-guidelines/) and [Nielsen Norman Group’s chatbot design guidance](https://www.nngroup.com/articles/ai-chatbots-design-guidelines/), particularly clear expectations, source visibility, easy correction, and user control.
