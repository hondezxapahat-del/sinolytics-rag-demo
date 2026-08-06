# Sinolytics RAG Demo

A retrieval-augmented Q&A demo over China policy/tech briefings, paired with a standalone data visualization script for market analysis.

## Background

This project was built as a technical proof-of-concept for the **Working Student – Data and AI Application** role at Sinolytics. It is meant to demonstrate, end to end, how a small but production-shaped RAG pipeline and a lightweight data visualization workflow can be built with a modern Python/JS stack.

## Tech Stack

- **Python** — backend logic, embedding pipeline, data visualization
- **FastAPI** — REST API serving the Q&A endpoint
- **OpenAI API** — `text-embedding-3-small` for embeddings, `gpt-4o-mini` for answer generation
- **Supabase (Postgres + pgvector)** — vector storage and similarity search
- **HTML / CSS / JavaScript** — vanilla frontend (no framework), talks to the API via `fetch`
- **pandas / matplotlib** — data loading and charting for the visualization script

## Architecture

```
Source documents (.txt)
        │
        ▼
   Chunking (sentence-aware, ~500 chars/chunk)
        │
        ▼
   Embedding (OpenAI text-embedding-3-small)
        │
        ▼
   Vector store (Supabase / pgvector)
        │
        ▼
   Semantic retrieval (cosine similarity, top-k)
        │
        ▼
   LLM answer generation (gpt-4o-mini, context-constrained prompt)
        │
        ▼
   Frontend (ask.html)
```

## Feature Modules

### 1. RAG Q&A System

- `embed_and_store.py` — reads `.txt` files from `docs/`, splits them into sentence-aware chunks (~500 characters each), embeds every chunk with OpenAI, and writes the results into a Supabase `documents` table.
- `match_documents.sql` — a Postgres/pgvector RPC function that ranks chunks by cosine similarity (`<=>` operator) against a query embedding.
- `retrieval.py` / `search.py` — shared retrieval logic and a small CLI for testing semantic search directly, outside the API.
- `api.py` — FastAPI service exposing `POST /ask`. It embeds the incoming question, retrieves the top-k matching chunks from Supabase, and prompts `gpt-4o-mini` to answer **strictly from the retrieved context**. The response includes both the generated answer and the source chunks with their similarity scores.
- `ask.html` / `index.html` — a minimal static frontend (no build step) that calls the API and renders the answer.

### 2. Data Visualization Script

- `plot_price_trend.py` — reads `china_nev_price_war.csv` with pandas and plots average price per brand over time with matplotlib, exporting a presentation-ready `price_trend.png`. This module is independent of the RAG pipeline and demonstrates a quick raw-data-to-chart workflow (e.g., for market/pricing analysis).

## Technical Challenges & Solutions

- **Supabase RLS/permissions** — default Row Level Security blocked server-side reads/writes to the `documents` table. Resolved by using the Supabase **service role key** for backend operations (embedding storage and retrieval), while keeping it out of the frontend entirely.
- **Anti-hallucination prompt design** — the LLM prompt explicitly restricts the model to answering only from the retrieved chunks, and instructs it to say it doesn't know when the context doesn't cover the question, rather than falling back on general knowledge.
- **Chunk granularity vs. retrieval quality** — fixed-length slicing produced chunks that cut sentences mid-thought and hurt retrieval precision. Switching to sentence-aware chunking at ~500 characters improved match relevance while keeping each chunk coherent enough for the LLM to use as context.

## Data Used

- **Retrieval corpus**: publicly released Sinolytics whitepapers and briefings (e.g., an export-controls whitepaper and short China tech/policy briefs), used as the knowledge base for the Q&A demo.
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
4. In the Supabase SQL editor, run `match_documents.sql` once to create the similarity search function.
5. Embed and store the source documents:
   ```bash
   python embed_and_store.py
   ```
6. Start the API:
   ```bash
   uvicorn api:app --reload
   ```
7. Open `ask.html` in a browser and ask a question.
8. (Optional) Regenerate the price trend chart:
   ```bash
   python plot_price_trend.py
   ```

## Future Directions

- Multimodal document parsing (PDF, tables, scanned reports) instead of plain `.txt` input
- Hybrid search (keyword + vector) to improve recall on named entities and acronyms
- Connecting visualization outputs to a BI tool (e.g., Power BI, Metabase) for a live dashboard
- A retrieval/answer evaluation harness to track hallucination rate and answer relevance over time
- Authentication and rate limiting for shared, multi-user access
