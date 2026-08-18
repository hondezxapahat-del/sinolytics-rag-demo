-- Run this once in the Supabase SQL Editor. Backs the lightweight
-- username+password login and the conversation-history sidebar
-- (PRD_v1.1.md Goal 8 / Requirement 13a-13b).
--
-- conversation_threads is a thin ownership/title index on top of the
-- LangGraph checkpointer's own tables (created by setup_checkpointer.py) —
-- the checkpointer stores the actual message history, this table only
-- tracks "which session_id belongs to which user, with what title."

create table if not exists users (
  id bigint generated always as identity primary key,
  username text not null unique,
  password_hash text not null,
  created_at timestamptz not null default now()
);

create table if not exists conversation_threads (
  session_id text primary key,
  user_id bigint not null references users (id) on delete cascade,
  title text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists conversation_threads_user_idx
  on conversation_threads (user_id, updated_at desc);
