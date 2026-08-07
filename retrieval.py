"""Shared retrieval logic: embed a question and fetch similar chunks from Supabase."""

import os
import re

from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client

EMBEDDING_MODEL = "text-embedding-3-small"
RERANK_MODEL = "gpt-4o-mini"
MATCH_COUNT = 3

load_dotenv()

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"]

openai_client = OpenAI(api_key=OPENAI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def embed_query(text):
    response = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def search(question, match_count=MATCH_COUNT):
    query_embedding = embed_query(question)
    result = supabase.rpc(
        "match_documents",
        {"query_embedding": query_embedding, "match_count": match_count},
    ).execute()
    return result.data


def keyword_search(query, match_count=MATCH_COUNT):
    result = supabase.rpc(
        "keyword_search",
        {"query_text": query, "match_count": match_count},
    ).execute()
    return result.data


def hybrid_search(question, match_count=MATCH_COUNT):
    """Merge vector search (match_documents) and keyword search (keyword_search)
    into one deduped candidate set, keyed by row id."""
    vector_matches = search(question, match_count)
    keyword_matches = keyword_search(question, match_count)

    candidates = {}
    for m in vector_matches:
        candidates[m["id"]] = {
            "id": m["id"],
            "content": m["content"],
            "similarity": m["similarity"],
            "rank": None,
        }
    for m in keyword_matches:
        existing = candidates.get(m["id"])
        if existing:
            existing["rank"] = m["rank"]
        else:
            candidates[m["id"]] = {
                "id": m["id"],
                "content": m["content"],
                "similarity": None,
                "rank": m["rank"],
            }

    return list(candidates.values())


def score_relevance_batch(question, contents):
    """Score every candidate's relevance to the question in a single LLM call
    (one prompt listing all candidates, one response with all scores) instead
    of one call per candidate — this is the expensive part of rerank, so
    batching it is what actually cuts the call count down."""
    if not contents:
        return []

    numbered = "\n\n".join(f"[{i}] {content}" for i, content in enumerate(contents))
    prompt = (
        "Rate how relevant each numbered passage below is to the question, on "
        "a scale from 0 (not relevant at all) to 10 (highly relevant).\n\n"
        f"Question: {question}\n\n"
        f"Passages:\n{numbered}\n\n"
        "Respond with exactly one line per passage, in the format "
        "'[index]: score', and nothing else. Example:\n[0]: 7\n[1]: 2"
    )
    response = openai_client.chat.completions.create(
        model=RERANK_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.choices[0].message.content.strip()

    scores = {}
    for line in text.splitlines():
        match = re.match(r"\[?(\d+)\]?\s*[:.\-]\s*(\d+(\.\d+)?)", line.strip())
        if match:
            index = int(match.group(1))
            scores[index] = max(0.0, min(10.0, float(match.group(2))))

    # Any passage the model didn't return a line for is treated as 0 —
    # missing a score is not the same as being relevant.
    return [scores.get(i, 0.0) for i in range(len(contents))]


def rerank(question, candidates, top_n=3):
    """Score all candidates' relevance to the question in one batched LLM
    call, then return the top_n highest-scoring ones."""
    if not candidates:
        return []

    scores = score_relevance_batch(question, [c["content"] for c in candidates])
    scored = [
        {**candidate, "relevance_score": score}
        for candidate, score in zip(candidates, scores)
    ]
    scored.sort(key=lambda c: c["relevance_score"], reverse=True)
    return scored[:top_n]
