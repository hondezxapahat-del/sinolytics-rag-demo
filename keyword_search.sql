-- Run this once in the Supabase SQL Editor to add full-text keyword search.
-- Assumes table "documents" has columns id bigint, content text.

-- Speeds up the tsvector match/rank below; without it every call does a full scan.
create index if not exists documents_content_fts_idx
  on documents
  using gin (to_tsvector('english', content));

create or replace function keyword_search (
  query_text text,
  match_count int default 3
)
returns table (
  id bigint,
  content text,
  rank float
)
language sql stable
as $$
  select
    documents.id,
    documents.content,
    ts_rank(to_tsvector('english', documents.content), plainto_tsquery('english', query_text)) as rank
  from documents
  where to_tsvector('english', documents.content) @@ plainto_tsquery('english', query_text)
  order by rank desc
  limit match_count;
$$;
