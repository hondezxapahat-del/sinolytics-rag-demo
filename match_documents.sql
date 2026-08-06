-- Run this once in the Supabase SQL Editor to create the similarity search function.
-- Assumes: extension "vector" is enabled, and table "documents" has columns
--   id bigint, content text, embedding vector(1536)

create or replace function match_documents (
  query_embedding vector(1536),
  match_count int default 3
)
returns table (
  id bigint,
  content text,
  similarity float
)
language sql stable
as $$
  select
    documents.id,
    documents.content,
    1 - (documents.embedding <=> query_embedding) as similarity
  from documents
  order by documents.embedding <=> query_embedding
  limit match_count;
$$;
