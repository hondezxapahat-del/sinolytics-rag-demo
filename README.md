# Sinolytics RAG Demo

A retrieval-augmented Q&A agent over China policy/tech briefings — with function-calling tool use, hybrid (vector + keyword) retrieval, LLM reranking, and on-demand chart generation — paired with a small marketing frontend.

## Background

This project was built as a technical proof-of-concept for the **Working Student – Data and AI Application** role at Sinolytics. It demonstrates, end to end, how a small but production-shaped RAG pipeline, an LLM agent with tool use, and a lightweight data visualization workflow can be built with a modern Python/JS stack.

## Tech Stack

- **Python** — backend logic, embedding pipeline, data visualization
- **FastAPI** — REST API serving the agent endpoint
- **OpenAI API** — `text-embedding-3-small` for embeddings, `gpt-4o-mini` for function calling, reranking, and answer generation
- **Supabase (Postgres + pgvector)** — vector storage, cosine-similarity search, and full-text keyword search
- **HTML / CSS / JavaScript** — vanilla frontend (no framework), talks to the API via `fetch`
- **pandas / matplotlib** — data loading and charting for the visualization tool

## Architecture

```
User question
      │
      ▼
FastAPI /ask ── gpt-4o-mini decides (function calling):
      │             │                    │
      │      no tool needed      search_documents(query)      generate_chart(topic)
      │       (e.g. greeting)            │                          │
      │             │           Hybrid retrieval:                topic keyword
      │             │        match_documents (vector)             match? ──no──▶ report
      │             │      + keyword_search (full-text)                          unavailable
      │             │        merged & deduped by id                  │yes
      │             │                    │                    run plot_price_trend.py
      │             │        LLM rerank (0-10 per candidate,     → price_trend.png
      │             │           top 3 kept)                          │
      │             │                    │                    base64-encode image
      │             │        gpt-4o-mini answers from                │
      │             │        the top 3 chunks only                   │
      │             ▼                    ▼                           ▼
      └───────────────────── final answer synthesis (gpt-4o-mini) ───┘
                                          │
                                          ▼
                          { answer, sources[], chart_image? }
                                          │
                                          ▼
                                     ask.html
```

## Feature Modules

### 1. Ingestion pipeline

- `embed_and_store.py` — reads `.txt` files from `docs/` (optionally a specific file passed as a CLI arg, to add new documents without re-embedding everything), splits them into sentence-aware chunks (~500 characters each), embeds every chunk with OpenAI, and writes the results into a Supabase `documents` table.

### 2. Retrieval: hybrid search + LLM reranking

- `match_documents.sql` — a Postgres/pgvector RPC function that ranks chunks by cosine similarity (`<=>` operator) against a query embedding.
- `keyword_search.sql` — a Postgres full-text search RPC function (`to_tsvector` / `ts_rank` / `plainto_tsquery`, backed by a GIN index) that ranks chunks by keyword relevance, catching exact terms and acronyms that embeddings can miss.
- `retrieval.py` — shared retrieval logic:
  - `search()` — vector-only search via `match_documents`.
  - `keyword_search()` — full-text search via the `keyword_search` RPC.
  - `hybrid_search()` — merges both result sets into one deduped candidate pool, keyed by row id.
  - `rerank()` — scores each candidate's relevance to the question on a 0–10 scale with one `gpt-4o-mini` call per candidate, then returns the top N.
- `search.py` — CLI for testing hybrid retrieval directly, outside the API (prints each match's similarity/keyword-rank).

### 3. Agent API

- `api.py` — FastAPI service exposing `POST /ask`. The question first goes to `gpt-4o-mini` with two tools defined via function calling:
  - **`search_documents(query)`** — runs `hybrid_search` → `rerank` (top 3) → answers strictly from those chunks. Returns the answer plus its source chunks and their relevance scores.
  - **`generate_chart(topic)`** — only called for time-trend, comparison, share/proportion, or explicit visualization requests (not plain conceptual questions). Currently backs exactly one chart (China's NEV/EV price war by brand); if the topic doesn't match, the tool reports no chart is available instead of guessing. On success it runs `plot_price_trend.py`, base64-encodes the resulting PNG, and returns it as `chart_image` (kept out of the model's own context to avoid burning tokens on image bytes).
  - Plain greetings/small talk get answered directly, with no tool call.
  - A second `gpt-4o-mini` call synthesizes the final answer once tool results are available.
- CORS is enabled (`allow_origins=["*"]`) so the static frontend can call the API from a `file://` origin.

### 4. Frontend

- `index.html` — the marketing landing page (white background, black text, `#a4161a` red accent), linking into the ask page.
- `ask.html` — the chat-style ask page. Calls `POST /ask`, renders `answer` as text, and — only when the response includes `chart_image` — renders it as an `<img>` with a rounded border and soft shadow below the answer. Source chunks/relevance scores are not shown in the UI.

### 5. Data visualization tool

- `plot_price_trend.py` — reads `china_nev_price_war.csv` with pandas and plots average price per brand over time with matplotlib, exporting `price_trend.png`. Invoked either directly or by the agent's `generate_chart` tool.

## Technical Challenges & Solutions

- **Supabase RLS/permissions** — default Row Level Security blocked server-side reads/writes to the `documents` table. Resolved by using the Supabase **service role key** for backend operations, kept out of the frontend entirely.
- **Anti-hallucination prompt design** — the answer-generation prompt explicitly restricts the model to the retrieved chunks and instructs it to say it doesn't know when the context doesn't cover the question, rather than falling back on general knowledge. It also forces English output regardless of the source language, and asks for detailed rather than terse answers.
- **Chunk granularity vs. retrieval quality** — fixed-length slicing produced chunks that cut sentences mid-thought and hurt retrieval precision. Switching to sentence-aware chunking at ~500 characters improved match relevance while keeping each chunk coherent enough for the LLM to use as context.
- **Vector-only recall gaps** — pure embedding search sometimes missed passages containing exact keywords/acronyms. Adding full-text keyword search alongside vector search, merged into one candidate pool, improved recall before the more expensive reranking step narrows it back down.
- **Reranking cost/latency tradeoff** — scoring each candidate individually with an LLM call (rather than batching) adds several extra round-trips per question (~5–8 calls), noticeably slowing `/ask` down. This is a deliberate accuracy-over-latency choice for a demo; a production version would batch the scoring prompt or use a dedicated reranker model.
- **Chart tool scope** — `generate_chart` only backs one real chart, so its tool description and a keyword check both constrain when the agent calls it, and it reports "no matching chart" rather than silently rendering an unrelated image.

## Data Used

- **Retrieval corpus**: publicly released Sinolytics whitepapers and briefings (an export-controls whitepaper, plus short China AI/tech market briefs), used as the knowledge base for the Q&A agent.
- **Visualization dataset**: `china_nev_price_war.csv` contains **simulated data for demonstration purposes only** and does not represent real market figures.

## How to Run

1. Clone the repository and `cd` into it.
2. Install dependencies:
   ```bash
   pip install fastapi uvicorn openai supabase python-dotenv pandas matplotlib
   ```
3. Create a `.env` file with:
   ```
   OPENAI_API_KEY=...
   SUPABASE_URL=...
   SUPABASE_SERVICE_ROLE_KEY=...
   ```
4. In the Supabase SQL editor, run `match_documents.sql` and `keyword_search.sql` once to create the retrieval functions (and the full-text index).
5. Embed and store the source documents:
   ```bash
   python embed_and_store.py
   ```
   To add a new document later without re-embedding everything, pass its path directly: `python embed_and_store.py docs/new_file.txt`.
6. Start the API:
   ```bash
   uvicorn api:app --reload
   ```
7. Open `index.html` in a browser, click through to the ask page, and ask a question — try a factual question, a trend/comparison question (triggers the chart), and a plain greeting to see all three agent paths.
8. (Optional) Test retrieval directly from the CLI: `python search.py "your question"`.
9. (Optional) Regenerate the price trend chart standalone: `python plot_price_trend.py`.

## Future Directions

- Multimodal document parsing (PDF, tables, scanned reports) instead of plain `.txt` input
- Batch the reranking step into a single LLM call per question instead of one call per candidate, to cut latency
- More chart topics/datasets behind `generate_chart`, rather than one hardcoded chart
- Connecting visualization outputs to a BI tool (e.g., Power BI, Metabase) for a live dashboard
- A retrieval/answer evaluation harness to track hallucination rate and answer relevance over time
- Authentication and rate limiting for shared, multi-user access
