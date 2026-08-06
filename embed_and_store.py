"""Chunk txt files in docs/, embed each chunk with OpenAI, and store in Supabase."""

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client

DOCS_DIR = Path(__file__).parent / "docs"
EMBEDDING_MODEL = "text-embedding-3-small"
CHUNK_SIZE = 500  # approx characters per chunk
TABLE_NAME = "documents"

load_dotenv()

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"]

openai_client = OpenAI(api_key=OPENAI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？.!?])\s*")


def split_into_sentences(text):
    sentences = SENTENCE_SPLIT_RE.split(text)
    return [s.strip() for s in sentences if s.strip()]


def chunk_text(text, chunk_size=CHUNK_SIZE):
    sentences = split_into_sentences(text)
    chunks = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > chunk_size:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip() if current else sentence
    if current:
        chunks.append(current.strip())
    return chunks


def embed_chunk(text):
    response = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def main():
    if len(sys.argv) > 1:
        txt_files = [Path(arg) for arg in sys.argv[1:]]
    else:
        txt_files = sorted(DOCS_DIR.glob("*.txt"))
    if not txt_files:
        print(f"No .txt files found in {DOCS_DIR}")
        return

    rows = []
    for path in txt_files:
        text = path.read_text(encoding="utf-8")
        chunks = chunk_text(text)
        for chunk in chunks:
            embedding = embed_chunk(chunk)
            rows.append(
                {
                    "content": chunk,
                    "embedding": embedding,
                }
            )
        print(f"{path.name}: {len(chunks)} chunks")

    if rows:
        supabase.table(TABLE_NAME).insert(rows).execute()

    print(f"Total chunks stored: {len(rows)}")


if __name__ == "__main__":
    main()
