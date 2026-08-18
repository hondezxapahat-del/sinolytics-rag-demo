"""One-time setup: create the tables LangGraph's PostgresSaver needs for
conversation-history persistence (docs/TechSpec_v1.1.md §4.5). Run this once
per database, the same way match_documents.sql / keyword_search.sql are run
once in the Supabase SQL editor.

Usage: python setup_checkpointer.py
Requires SUPABASE_DB_URL in .env (a direct Postgres connection string from
Supabase's Database settings — not the same as SUPABASE_URL).
"""

import os

from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver

load_dotenv()

SUPABASE_DB_URL = os.environ["SUPABASE_DB_URL"]


def main():
    with PostgresSaver.from_conn_string(SUPABASE_DB_URL) as checkpointer:
        checkpointer.setup()
    print("Checkpointer tables created.")


if __name__ == "__main__":
    main()
