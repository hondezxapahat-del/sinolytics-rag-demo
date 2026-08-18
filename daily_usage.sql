-- Run this once in the Supabase SQL Editor. Backs a global daily cap on
-- /ask calls (not per-account) — protects against the shared demo running
-- up API costs, whether from a malicious signup or just heavier-than-
-- expected legitimate use. See docs/PRD_v1.2.md-adjacent decision made
-- directly in conversation (not a separate formal doc for this one).

create table if not exists daily_usage (
  usage_date date primary key,
  count integer not null default 0
);
