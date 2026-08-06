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


def score_relevance(question, content):
    response = openai_client.chat.completions.create(
        model=RERANK_MODEL,
        messages=[
            {
                "role": "user",
                "content": (
                    "Rate how relevant the following passage is to the question, "
                    "on a scale from 0 (not relevant at all) to 10 (highly relevant). "
                    "Respond with only the number, no other text.\n\n"
                    f"Question: {question}\n\n"
                    f"Passage:\n{content}\n\n"
                    "Score:"
                ),
            }
        ],
    )
    text = response.choices[0].message.content.strip()
    match = re.search(r"\d+(\.\d+)?", text)
    if not match:
        return 0.0
    return max(0.0, min(10.0, float(match.group())))


def rerank(question, candidates, top_n=3):
    """Score each candidate's relevance to the question with one LLM call per
    candidate, then return the top_n highest-scoring ones."""
    scored = [
        {**candidate, "relevance_score": score_relevance(question, candidate["content"])}
        for candidate in candidates
    ]
    scored.sort(key=lambda c: c["relevance_score"], reverse=True)
    return scored[:top_n]
