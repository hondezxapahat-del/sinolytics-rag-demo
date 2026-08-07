# Sinolytics RAG Demo

A LangChain tool-calling agent over China policy/tech briefings — hybrid (vector + keyword) retrieval with batched LLM reranking, on-demand chart generation, live web search cross-checked against the internal knowledge base, and multi-turn conversation memory — paired with a small marketing frontend.

## Background

This project was built as a technical proof-of-concept for the **Working Student – Data and AI Application** role at Sinolytics. It demonstrates, end to end, how a small but production-shaped RAG pipeline, an LLM agent with tool use, and a lightweight data visualization workflow can be built with a modern Python/JS stack.

## Tech Stack

- **Python** — backend logic, embedding pipeline, data visualization
- **FastAPI** — REST API serving the agent endpoint
- **LangChain** (`langchain`, `langchain-openai`, `langchain-tavily`) — `create_agent` tool-calling loop that routes each question to the right tool
- **OpenAI API** — `text-embedding-3-small` for embeddings, `gpt-4o-mini` for agent routing, reranking, and answer generation
- **Tavily API** — live web search, used only when a question needs current information
- **Supabase (Postgres + pgvector)** — vector storage, cosine-similarity search, and full-text keyword search
- **HTML / CSS / JavaScript** — vanilla frontend (no framework), talks to the API via `fetch`
- **pandas / matplotlib** — data loading and charting for the visualization tool

## Architecture

```
User question (+ recent conversation history)
      │
      ▼
FastAPI /ask ── LangChain agent (create_agent, gpt-4o-mini) decides, in order:
      │
      ├─ no tool needed (e.g. greeting) ─────────────────────────────▶ answer directly
      │
      ├─ explicit chart/graph/plot ask ──▶ generate_chart(topic)
      │                                         │
      │                              topic keyword match?
      │                              no ─▶ report unavailable
      │                              yes ─▶ run plot_price_trend.py
      │                                      → price_trend.png → base64
      │
      ├─ timeliness signal ('latest', 'trend', ...) ──▶ web_search(query)
      │        (fires even on a follow-up — never skipped just because      │
      │         the conversation already covered the topic)                 │
      │                                                                     ▼
      │                                              ┌─────────── run in parallel ───────────┐
      │                                              │                                        │
      │                                       Tavily search (topic=news)          search_documents(query)
      │                                       → per-result content/url/date        (same path as below)
      │                                       → 1 batched LLM call condenses        only surfaced if it
      │                                         each result into its own point       clears RELEVANCE_THRESHOLD
      │                                              │                                        │
      │                                              └──────────────┬─────────────────────────┘
      │                                                             ▼
      │                                          { web_findings[], internal_analysis? }
      │
      └─ other factual/analytical question ──▶ search_documents(query)
                                                      │
                                          hybrid_search: match_documents (vector)
                                              + keyword_search (full-text)
                                              merged & deduped by id
                                                      │
                                          1 batched LLM call reranks ALL
                                          candidates at once (0–10 each)
                                                      │
                                          chunks below MIN_CONTEXT_SCORE
                                          dropped before they reach the
                                          answer prompt (no padding)
                                                      │
                                          gpt-4o-mini answers strictly from
                                          the surviving chunks, structured
                                          as a consulting brief
                                                      │
                                          expert_note only generated if the
                                          top score clears RELEVANCE_THRESHOLD
                                                      ▼
                     final answer synthesis (gpt-4o-mini, aware of tool results)
                                          │
                                          ▼
       { answer, source_type, sources[]/expert_note, web_findings[]/internal_analysis,
                                chart_image? }
                                          │
                                          ▼
                                     ask.html
```

## Feature Modules

### 1. Ingestion pipeline

- `embed_and_store.py` — reads `.txt` files from `docs/` (optionally a specific file passed as a CLI arg, to add new documents without re-embedding everything), splits them into sentence-aware chunks (~500 characters each), embeds every chunk with OpenAI, and writes the results into a Supabase `documents` table.

### 2. Retrieval: hybrid search + batched LLM reranking

- `match_documents.sql` — a Postgres/pgvector RPC function that ranks chunks by cosine similarity (`<=>` operator) against a query embedding.
- `keyword_search.sql` — a Postgres full-text search RPC function (`to_tsvector` / `ts_rank` / `plainto_tsquery`, backed by a GIN index) that ranks chunks by keyword relevance, catching exact terms and acronyms that embeddings can miss.
- `retrieval.py` — shared retrieval logic:
  - `search()` — vector-only search via `match_documents`.
  - `keyword_search()` — full-text search via the `keyword_search` RPC.
  - `hybrid_search()` — merges both result sets into one deduped candidate pool, keyed by row id.
  - `rerank()` — scores **all** candidates' relevance to the question (0–10) in a **single** batched LLM call (one prompt listing every candidate, one response with every score), then returns the top N. Started as one call per candidate; batching cut the call count from N down to 1.
- `search.py` — CLI for testing hybrid retrieval directly, outside the API (prints each match's similarity/keyword-rank).

### 3. Agent (`agent.py`)

LangChain's `create_agent` (the current `langchain.agents` API — `create_tool_calling_agent` + `AgentExecutor` were removed in LangChain 1.x) runs a tool-calling loop over three tools, guided by an ordered, keyword-anchored system prompt so routing is fast and deterministic rather than deliberated:

1. Greeting/small talk → answer directly, no tool.
2. Explicit chart/graph/plot ask, or a comparison/share question about the EV price war → `generate_chart`.
3. A timeliness signal (`latest`, `trend`, `this year`, `最新`, `趋势`, ...) → `web_search`, **even on a follow-up** — being a follow-up is never a reason to skip a fresh search when the question itself asks for current information.
4. Anything else factual/analytical → `search_documents`.

It also carries the last few turns of conversation history (`conversation_history` in the request) and is explicitly instructed to only treat a new question as connected to prior turns when it's genuinely a follow-up — never fabricating a connection between unrelated topics just because they share a conversation.

### 4. Core tool implementations (`tools.py`)

Kept independent of the LangChain wiring, so retrieval/chart behavior doesn't depend on how the agent routes to it:

- **`search_documents(query)`** — `hybrid_search` → `rerank` → drops chunks below `MIN_CONTEXT_SCORE` (rerank always returns exactly N candidates regardless of relevance; without this filter, weak/tangential chunks got padded into the answer prompt and the model dutifully turned them into extra bullet points) → answers strictly from what's left, formatted as a consulting brief. `expert_note` (a one-line "prior analysis" callout) is only generated when the top score clears `RELEVANCE_THRESHOLD` — never to sound experienced on a weak match.
- **`generate_chart(topic)`** — only called for time-trend/comparison/share/explicit-visualization requests. Currently backs exactly one chart (China's NEV/EV price war by brand); if the topic doesn't match, it reports no chart is available instead of guessing. On success it runs `plot_price_trend.py` and returns the PNG as raw base64.
- **`search_web(query)`** — runs a Tavily search and an internal `search_documents` check **in parallel** (`ThreadPoolExecutor`). Tavily is queried with `topic="news"` specifically because that's what makes it return `published_date` per result — the default topic usually doesn't. Each result is condensed into its own one-sentence point via a single batched LLM call (one prompt listing every excerpt, so each point stays grounded in exactly one source — no mixing content across sources, which would make citations unreliable). `internal_analysis` is only included when the parallel internal search clears the same `RELEVANCE_THRESHOLD` used elsewhere.

### 5. API layer (`api.py`)

Thin FastAPI wrapper: `POST /ask` takes `{question, conversation_history, match_count}` and calls `agent.run_agent(...)`. Response shape:

```
{
  answer, source_type,               // "internal" or "web"
  sources[], expert_note,            // populated on the search_documents path
  web_findings[], internal_analysis, // populated on the web_search path
  chart_path, chart_image            // populated on the generate_chart path
}
```

`web_findings` items are `{content, source, url, date}` — `date` is `null` whenever Tavily didn't provide one; it's never guessed. CORS is enabled (`allow_origins=["*"]`) so the static frontend can call the API from a `file://` origin.

### 6. Frontend

- `index.html` — the marketing landing page (white background, black text, `#a4161a` red accent), linking into the ask page; the "Sinolytics" wordmark on the ask page links back here.
- `ask.html` — the chat-style ask page. Maintains conversation history client-side and sends the last few turns with every request. Renders answers through a small markdown renderer (bold + bullets). On the web-search path, `web_findings` render as individual blocks (content + small-text source/date, source name linked to the original URL) instead of free prose, so a point can't visually detach from its citation; `internal_analysis`, when present, renders as its own visually distinct block titled "Sinolytics' prior analysis on this topic". Chart images render inline with a rounded border and soft shadow.

### 7. Data visualization tool

- `plot_price_trend.py` — reads `china_nev_price_war.csv` with pandas and plots average price per brand over time with matplotlib, exporting `price_trend.png`. Invoked either directly or by the agent's `generate_chart` tool.

## Technical Challenges & Solutions

- **Supabase RLS/permissions** — default Row Level Security blocked server-side reads/writes to the `documents` table. Resolved by using the Supabase **service role key** for backend operations, kept out of the frontend entirely.
- **Anti-hallucination prompt design** — the answer-generation prompt restricts the model to the retrieved chunks, forces English output regardless of source language, and explicitly separates "use everything the source actually contains" from "never pad with your own general knowledge to look more thorough" — a short answer from thin source material is treated as correct, not a shortcoming to compensate for.
- **Chunk granularity vs. retrieval quality** — fixed-length slicing produced chunks that cut sentences mid-thought. Sentence-aware chunking at ~500 characters improved match relevance while keeping each chunk coherent.
- **Vector-only recall gaps** — pure embedding search sometimes missed passages containing exact keywords/acronyms. Full-text keyword search alongside vector search, merged into one candidate pool, improved recall before reranking narrows it back down.
- **Reranking cost/latency** — originally one LLM call per candidate (5–10 calls per question). Batched into a single call that scores every candidate at once, cutting a typical `/ask` request from ~9 LLM calls down to ~5.
- **Context padding from low-relevance chunks** — `rerank` always returns exactly top-N candidates regardless of how relevant they actually are, so even a narrow single-fact question was getting 2-3 near-noise chunks padded into the answer prompt, which the model then dutifully expanded into extra bullet points. Fixed by dropping chunks below `MIN_CONTEXT_SCORE` before they ever reach the prompt.
- **LangChain 1.x API migration** — `create_tool_calling_agent` + `AgentExecutor` (the legacy agent API) were removed in LangChain 1.x in favor of `create_agent` (LangGraph-based). Tool outputs that need to carry structured data back to the API response (chart images, source lists, web findings) don't fit neatly through the new agent's plain-text tool-result channel, so tools write into a per-request `capture` dict via closures instead — the LLM still only sees a short text acknowledgment.
- **Web search citation reliability** — asking an LLM to freely narrate across multiple search results risks misattributing a claim to the wrong source. Instead, each Tavily result is condensed independently (one prompt, but explicitly one-point-per-excerpt, no cross-referencing) so every `web_finding` traces to exactly one URL/date, and a missing date is left `null` rather than inferred.
- **Chart tool scope** — `generate_chart` only backs one real chart, so its tool description and a keyword check both constrain when the agent calls it, and it reports "no matching chart" rather than silently rendering an unrelated image.
- **Follow-up vs. stale-answer tension** — the agent is told to treat genuine follow-ups as connected to prior turns, but that default would let a follow-up like "what's the *latest* on this?" get answered from conversation history instead of a fresh search. The timeliness rule explicitly overrides the follow-up rule when both apply.

## Data Used

- **Retrieval corpus**: publicly released Sinolytics whitepapers and briefings (an export-controls whitepaper, plus short China AI/tech market briefs), used as the knowledge base for the Q&A agent.
- **Visualization dataset**: `china_nev_price_war.csv` contains **simulated data for demonstration purposes only** and does not represent real market figures.

## How to Run

1. Clone the repository and `cd` into it.
2. Install dependencies:
   ```bash
   pip install fastapi uvicorn openai supabase python-dotenv pandas matplotlib langchain langchain-openai langchain-tavily
   ```
3. Create a `.env` file with:
   ```
   OPENAI_API_KEY=...
   SUPABASE_URL=...
   SUPABASE_SERVICE_ROLE_KEY=...
   TAVILY_API_KEY=...
   ```
   `TAVILY_API_KEY` is optional — without it, the agent still works with the search/chart tools, and the web search tool activates automatically once the key is added (no code changes needed).
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
7. Open `index.html` in a browser, click through to the ask page, and try each agent path: a factual question, a trend/comparison question (triggers the chart), a timeliness question like "what's the latest news on X" (triggers web search + internal cross-check), and a plain greeting.
8. (Optional) Test retrieval directly from the CLI: `python search.py "your question"`.
9. (Optional) Regenerate the price trend chart standalone: `python plot_price_trend.py`.

## Future Directions

- Multimodal document parsing (PDF, tables, scanned reports) instead of plain `.txt` input
- More chart topics/datasets behind `generate_chart`, rather than one hardcoded chart
- Persist conversation history server-side (per session/user) instead of only in the browser tab
- Streaming responses, so the agent's progress is visible instead of a single blocking round-trip
- Connecting visualization outputs to a BI tool (e.g., Power BI, Metabase) for a live dashboard
- A retrieval/answer evaluation harness to track hallucination rate and answer relevance over time
- Authentication and rate limiting for shared, multi-user access
