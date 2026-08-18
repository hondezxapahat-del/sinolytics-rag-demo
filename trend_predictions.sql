-- Run this once in the Supabase SQL Editor to create the trend_predictions
-- table and its topic-matching function (docs/TechSpec_v1.1.md §4.2).
-- Assumes: extension "vector" is enabled (same as match_documents.sql).

create table if not exists trend_predictions (
  id bigint generated always as identity primary key,
  topic text not null,
  topic_embedding vector(1536) not null,
  draft_content text not null,
  status text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  created_at timestamptz not null default now(),
  reviewed_at timestamptz,
  reviewer_note text
);

create index if not exists trend_predictions_status_idx on trend_predictions (status);

-- Finds the closest existing prediction (any status) to a new topic, so the
-- Python side can decide: reuse an approved one, report "pending", or
-- generate a new draft. match_threshold is a cosine-similarity cutoff
-- (1 - cosine distance) — 0.85 is a starting guess, not a validated value;
-- see the "similarly-worded topics" risk in docs/TechSpec_v1.1.md §5 and
-- tune this once real usage data exists.
create or replace function match_trend_prediction (
  query_embedding vector(1536),
  match_threshold float default 0.85
)
returns table (
  id bigint,
  topic text,
  draft_content text,
  status text
)
language sql stable
as $$
  -- Rejected drafts are excluded so a rejected topic always regenerates a
  -- fresh draft on the next ask, rather than a stale rejected row
  -- occasionally winning a distance tie against a newer pending one.
  select
    trend_predictions.id,
    trend_predictions.topic,
    trend_predictions.draft_content,
    trend_predictions.status
  from trend_predictions
  where trend_predictions.status in ('pending', 'approved')
    and 1 - (trend_predictions.topic_embedding <=> query_embedding) >= match_threshold
  order by trend_predictions.topic_embedding <=> query_embedding
  limit 1;
$$;
