# Sinolume RAG Demo — Technical Design v1.1

> This document is written against [PRD_v1.1.en.md](PRD_v1.1.en.md) and covers the parts the PRD explicitly deferred to "a later technical document" — evaluation methodology, internal/external fusion display, the human-confirmation workflow, and related design decisions.

## 1. Background and Goals

This document is written against [PRD_v1.1.en.md](PRD_v1.1.en.md) and covers the parts marked "left to a later technical document": how baseline is defined, evaluation methodology / ablation study design, the concrete implementation of the human-confirmation workflow, the design for internal/external fusion display, etc. (corresponds to PRD Open Questions #4, 6, 7, 9, 10).

**Goal**: turn the PRD's 7 P0 requirements (see PRD Goals & Non-Goals) into an executable technical design — which files change, what components get added, the key technology choices and the reasoning behind them, serving as the direct basis for implementation. P1 goals (multimodal parsing, additional charts, BI integration, multi-user auth) are not expanded in this document; per the PRD's Out of Scope section, they'll be designed separately later if and when they're picked up.

## 2. Current State Analysis

v1.0's implementation as of this writing:

- **Agent layer** (`agent.py`): built on LangChain's `create_agent` (LangGraph). The system prompt routes to one of three tools by priority: greetings/small talk get no tool call; chart/comparison questions call `generate_chart`; questions hitting a timeliness signal ("latest", "trend", "最新", "趋势", etc.) call `web_search`; everything else factual calls `search_documents`. Each call explicitly passes in the last few turns of conversation history (`conversation_history`); it does not use LangGraph's native checkpoint persistence.
- **Retrieval layer** (`retrieval.py`): `hybrid_search` merges vector search (`match_documents` RPC) and keyword search (`keyword_search` RPC) results, deduped by id; `rerank` scores all candidates in a single batched LLM call (0-10), returning the top-N.
- **Tool implementations** (`tools.py`): `search_documents` filters out low-relevance chunks below `MIN_CONTEXT_SCORE` after reranking, and only generates an `expert_note` when the top score clears `RELEVANCE_THRESHOLD`; `generate_chart` supports exactly one topic (NEV price war) via keyword matching; `search_web` calls Tavily and internal retrieval in parallel via `ThreadPoolExecutor`, only attaching the internal result as `internal_analysis` when it clears the threshold, and uses `topic="news"` with Tavily to get publish dates.
- **API layer** (`api.py`): a single `POST /ask` endpoint taking `question` + `conversation_history` + `match_count`, CORS wide open (`allow_origins=["*"]`), no authentication.
- **Frontend** (`ask.html`): conversation history lives in browser memory, with the last few turns sent on every request; refreshing the page or closing the tab loses it.

**This current state maps directly to the gaps named in the PRD Problem Statement**:

- No evaluation/scoring mechanism → maps to "answer quality can't be quantifiably proven."
- No observability tooling of any kind, the only runtime information is local logs → maps to "runtime status and cost are invisible."
- History lives only in browser memory → maps to "conversation history doesn't persist."
- `/ask` has no input validation/protection logic at all → maps to "no protection against adversarial input."
- `web_search` already queries internal results in parallel, but only attaches them above a threshold, and whether it even runs at all depends entirely on whether routing hits a "timeliness signal" (rule 4 never queries external at all) → maps to "internal retrieval and web search are disconnected."
- The Tavily call has no time-window restriction and no query rewriting for timeliness questions → maps to "weak web search result quality."

## 3. Overall Architecture

v1.0 is a three-tool router (`search_documents` / `generate_chart` / `web_search`). v1.1's changes on top of that (detailed in each subsection of §4):

- A fourth tool, `generate_trend_prediction`, is added, with an asynchronous approval queue (`trend_predictions` table + a review page).
- ~~Routing rule 3 (timeliness signal) forces parallel calls to both `search_documents` and `web_search`~~ — re-checking the existing code confirmed this isn't needed: `web_search` already queries internal material in parallel internally. See §4.1.
- The way the Agent is invoked changes from "explicitly pass in a history list" to using a `PostgresSaver` checkpointer keyed by `session_id` (i.e. `thread_id`).
- LangSmith is integrated for end-to-end observability, without touching business logic.
- A lightweight input pre-filter is added at the request entry point; matches on solicitation patterns are rejected before ever reaching the Agent.
- The Tavily call inside `web_search` gains a time-window constraint and query rewriting.
- An independent evaluation pipeline is added — it's not in the live request path, it's an offline verification toolchain.

**Overall architecture diagram**:

```mermaid
flowchart TB
    subgraph Client[Frontend — ask.html]
        UI[Chat UI]
    end

    subgraph API[api.py]
        F[Input pre-filter<br/>rule/keyword matching]
    end

    subgraph Agent[agent.py — LangGraph Agent]
        RT[Routing decision<br/>hardened SYSTEM_PROMPT]
        CP[(PostgresSaver<br/>checkpointer)]
    end

    subgraph Tools[tools.py]
        SD[search_documents]
        GC[generate_chart]
        WS[web_search<br/>Tavily time window + query rewrite]
        GP[generate_trend_prediction]
    end

    subgraph Data[Supabase / Postgres]
        DOCS[(documents table<br/>vector + keyword index)]
        CHK[(checkpoint table)]
        PRED[(trend_predictions table)]
    end

    subgraph Review[review.html]
        RV[Human approve/reject]
    end

    subgraph Obs[LangSmith]
        TR[Call trace + cost tracking]
    end

    UI -->|question + session_id| F
    F -->|blocked, never reaches Agent| UI
    F --> RT
    RT <--> CP
    CP <--> CHK
    RT -->|rule 3 hit| WS
    RT -->|rule 2| GC
    RT -->|rule 4| SD
    RT -->|prediction keyword| GP
    SD --> DOCS
    GP --> PRED
    GP -.match approved records by topic.-> PRED
    RV <--> PRED
    RT -.trace reported.-> TR
    SD -.-> TR
    WS -.-> TR
    RT --> UI
```

**Design principles consistent across modules**:

- Reuse existing implementations wherever possible (`search_web`'s existing parallel-call pattern, `score_relevance_batch`'s batched-scoring pattern) — don't reinvent what's already there.
- New persistence/observability/review capability all goes through mature components already in the stack (Supabase Postgres, LangGraph's native checkpointer, LangSmith) — no new category of infrastructure is introduced.
- Every "lightweight" boundary (input protection, search-quality fix) stays within the Non-Goals the PRD already drew — the technical design doesn't overreach into problems the PRD explicitly excluded.

## 4. Detailed Design

4.1-4.7 below each correspond to one of the PRD's 7 P0 goals, expanding on its technical approach.

### 4.1 Internal/External Source Fusion and Display

**Corresponds to**: PRD Requirements 1, 2; Goals P0 #1.

**Finding after re-checking the current state: no new code needed.** Re-checking the existing code turned up that v1.0 already has this capability. `tools.py`'s `search_web()` already calls `search_documents` **in parallel** via `ThreadPoolExecutor` whenever it's invoked, bundling the internal result (`internal_analysis`) and the external result (`web_findings`) together into a single tool-call response; `agent.py`'s system prompt already has a rule that "any part of the answer drawing on the web search tool must be explicitly labeled as coming from a web search"; and `ask.html` already renders both as separate display blocks. In other words, whenever routing rule 3 (timeliness signal) hits and the Agent calls `web_search` once, internal/external fusion display already happens automatically — no further change is needed.

**Recording a design mistake**: this section's original plan was "have the Agent routing layer force calls to both `search_documents` and `web_search` as independent tool calls." That plan was designed without first checking the existing implementation, and turned out to be **redundant work** — `search_documents` would get run an extra time (an extra retrieval + rerank + generation cost), producing an `internal_analysis` that's identical to what the existing parallel mechanism already computes, with zero incremental value. That plan has been dropped in favor of just documenting the actual current state; §3's overall architecture diagram has been corrected to match.

**What's genuinely still unaddressed, but intentionally not being fixed**: routing rule 4 (a purely internal question with no timeliness signal) never retrieves external information at all — but that boundary was deliberately drawn by PRD Non-Goal #6 (not competing on whole-web comprehensiveness), so it isn't a gap that needs fixing.

**Disagreement display strategy (judgment unchanged)**: no extra "disagreement detection" step is needed. Internal and external results are already displayed side by side, each labeled by source — that structural constraint already holds in the existing implementation, and it naturally satisfies "faithfully present disagreement" (PRD Requirement 2) without needing an additional "disagreement judgment" model that would itself need to be evaluated.

**Flow (when the timeliness signal is hit — this is the current state, no change needed)**:

```mermaid
sequenceDiagram
    participant U as User
    participant A as Agent routing (agent.py)
    participant W as web_search tool
    U->>A: Question (contains a timeliness signal)
    A->>W: Call (this single tool call is all that happens)
    W->>W: Internally queries Tavily + search_documents in parallel
    W-->>A: web_findings[] (with source/date) + internal_analysis (only if relevance clears RELEVANCE_THRESHOLD)
    A->>U: Synthesized answer + two separate sections (external/internal)
```

**Suggested action**: no code to write, but this is worth specifically verifying in the §4.3 evaluation — run a handful of real "timeliness" questions through it and confirm `internal_analysis` and `web_findings` genuinely both show up, sourcing is clearly labeled, and nothing gets merged into a single statement. Close this out with real evaluation data, not with "it should work this way."

### 4.2 Trend Prediction + Human Confirmation Workflow

**Corresponds to**: PRD Requirements 3, 4, 5; Goals P0 #2; resolves PRD Open Question 7 (the tension between human confirmation and live demos).

**Integration**: add a fourth, independent Agent tool, `generate_trend_prediction(topic)`, alongside `search_documents` / `generate_chart` / `web_search`. A new routing rule is added: when a question hits a prediction/outlook-type keyword ("预测", "展望", "未来会怎样", "forecast", "outlook", etc.), this tool is called — it doesn't conflict with the three existing routing rules.

**Confirmation mechanism: an asynchronous approval queue that naturally grows into an "approved prediction library"**

- Add a `trend_predictions` table: `id`, `topic` (the raw topic text), `topic_embedding` (used for later topic matching), `draft_content` (the AI-generated draft prediction), `status` (pending / approved / rejected), `created_at`, `reviewed_at`, `reviewer_note`.
- **First time a topic is hit**: generate a draft prediction, write it to the table (`status=pending`); in that same conversation turn, honestly tell the user "this kind of forward-looking prediction needs human review, and there isn't a confirmed one yet" — the draft content itself is never shown, and the response falls back to a regular retrieval-based internal analysis (with no predictive framing). If that fallback analysis itself can't produce anything either (because internal retrieval doesn't clear `MIN_CONTEXT_SCORE`), the system must honestly say "there's currently neither an available prediction nor enough internal material on this topic" rather than returning something blank or erroring out — this double-empty edge case needs to be covered by the fallback logic.
- **When a semantically similar topic is asked again later** (by the same user or a different visitor): reuse the existing embedding-similarity search approach (no new matching algorithm) to check the approved library first — a hit on an approved record returns it directly; a hit on "pending" honestly reports "under review, not available yet"; only if there's no match at all does it go through the generation flow again.
- This way the queue naturally grows into an "approved prediction library" through actual use — the same topic doesn't need to go through approval every time, and there's no need to hand-craft a batch of topics ahead of time just for a demo.

**Review interface**: add a simple review page (e.g. `review.html` + a corresponding API endpoint), whose address only you know — it's not linked anywhere publicly and doesn't need an account system. This is an internal tool for your own use, and doesn't fall under the Non-Goal of "an authentication system for anonymous public users." The page lists all `pending` records' topics and draft content, offers approve/reject actions, and updates the corresponding record's `status`.

**How the "internal-analyst style" is achieved**: reuse the existing pattern in `tools.py`'s `summarize_prior_experience` — "a prompt plus a small number of internal-report excerpts as a style reference" — so the generated prediction's wording matches the tone of internal reports, without introducing a new modeling approach.

**Interface labeling**: corresponds to Requirement 5 — when an approved prediction is used in an answer, it must carry a clear, distinguishable label (a separate display block + a "human-confirmed prediction" tag), distinct from a plain retrieved answer.

**Flow**:

```mermaid
sequenceDiagram
    participant U as User
    participant A as Agent (generate_trend_prediction)
    participant DB as trend_predictions table
    participant R as Review page (you)

    U->>A: Question (hits a prediction keyword)
    A->>DB: Query approved records by topic embedding similarity
    alt Hits an approved record
        DB-->>A: Approved prediction content
        A->>U: Show it, labeled "human-confirmed prediction"
    else Hits a pending record
        DB-->>A: pending status
        A->>U: Honestly report "under review, not available yet"
    else No match
        A->>A: Generate a draft prediction
        A->>DB: Write a pending record
        A->>U: Honestly report "needs human review, not available yet" (falls back to a regular internal analysis)
    end

    Note over R,DB: Later, you open the review page
    R->>DB: Query all pending records
    R->>DB: approve / reject
```

### 4.3 Evaluation Methodology (Answer Quality vs. Baseline)

**Corresponds to**: PRD Requirements 6, 7, 8; Goals P0 #3; resolves Open Question 6 (baseline definition).

**Baseline definition**: the product's existing underlying model (`gpt-4o-mini`) answering the same question directly, with no retrieval whatsoever, serves as the baseline. Variables stay controlled — the only difference is "retrieval-augmented or not," with no confound from "swapped in a stronger/weaker model" — so this genuinely demonstrates the value the RAG architecture itself adds, rather than a difference in model capability.

**Evaluation metric suite**: no external evaluation library dependency — build an in-house evaluation script following the standard metric definitions from RAGAS-style methodology:

- **Faithfulness**: whether every statement in the answer is actually supported by the retrieved context — measures hallucination.
- **Context Precision / Recall**: how much of what was retrieved was actually needed (precision), and how much of what was needed got retrieved (recall).
- **Answer Relevancy**: whether the answer actually addresses the question asked.
- All of the above are scored by an LLM-as-judge (normalized to 0-10), with no need for human-labeled ground truth — reusing the existing "one batched call scores everything, instead of one call per item" pattern already used by `retrieval.py`'s `score_relevance_batch`.
- **Pairwise win rate**: anonymize "this product's answer" and "the baseline's answer" into A/B, and have the judge model pick which is better and explain why — this directly produces the "win rate" number referenced in Success Metric #6.

**Evaluation set construction**: hand-designed, covering the four topics actually present in the corpus (Chinese AI model pricing/market dynamics, China's desktop AI office-agent market, China's industrial robot installations, export controls — `china_nev_price_war.csv` is only used for chart generation and was never ingested into the retrieval store by `embed_and_store.py`, so it isn't a corpus topic), with roughly 5-10 representative questions per topic (about 20-40 total, consistent with the evaluation-pipeline diagram below), spanning different difficulty levels/types: single-fact questions, multi-point synthesis questions, questions the corpus doesn't cover (where the correct answer is honestly "I don't know"), and cross-topic confusion tests.

**Ablation study design**: for three independently-switchable components in the existing retrieval pipeline, run an A/B comparison for each:

1. **Hybrid retrieval vs. pure vector retrieval vs. pure keyword retrieval** — verifies the gain `hybrid_search` provides over either retrieval method alone.
2. **With/without LLM reranking** — verifies the actual contribution `rerank()`'s batched scoring step makes to final answer quality.
3. **With/without `MIN_CONTEXT_SCORE` filtering** — verifies whether filtering out low-relevance chunks genuinely reduces how much "filler" content dilutes the answer.

Each variant is run against the same evaluation set with the same metrics, for a like-for-like comparison.

**Evaluation pipeline**:

```mermaid
flowchart LR
    E[Eval set<br/>~20-40 questions] --> R1[Baseline<br/>direct answer, no retrieval]
    E --> R2[Full product<br/>hybrid+rerank+filter]
    E --> R3a[Ablation variant<br/>pure vector retrieval]
    E --> R3b[Ablation variant<br/>pure keyword retrieval]
    E --> R4[Ablation variant<br/>no reranking]
    E --> R5[Ablation variant<br/>no relevance filter]
    R1 --> J[LLM-as-judge<br/>metric scoring + pairwise win rate]
    R2 --> J
    R3a --> J
    R3b --> J
    R4 --> J
    R5 --> J
    J --> O[Evaluation report:<br/>per-variant metric scores / win rate vs. baseline / ablation deltas]
```

Six variants in total (baseline, full product, pure vector, pure keyword, no reranking, no relevance filter) — pure vector and pure keyword are two separate configurations and can't be collapsed into a single run; an earlier draft of this section miscounted them as one, corrected here.

**Scope note**: this section's evaluation/ablation only covers the existing `search_documents` retrieval pipeline — it does not cover 4.1's fusion display path or 4.2's trend-prediction path, which are v1.1's two most significant new capabilities. There is currently no evaluation method covering them. This is a known gap in this design, not something "already covered but just not written down" — a later iteration needs to design dedicated evaluation for those two paths rather than assuming the existing evaluation set validates them by proxy.

**Deliverable**: a reproducible evaluation report — each variant's score on each metric, its win rate against baseline, and an ablation-contribution table. This report is the actual artifact behind the PRD's "technical validation material worth presenting," and is the acceptance basis for Success Metrics #5 and #6.

### 4.4 Runtime Status and Cost Observability

**Corresponds to**: PRD Requirements 9, 10, 11; Goals P0 #4.

**Approach**: integrate LangSmith. The product's Agent layer is already built on LangChain's `create_agent` (LangGraph), and LangSmith integrates natively with that stack — just set the environment variables (`LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`) and every `agent.invoke(...)` call automatically reports its full call trace, with no changes needed to the business logic in `agent.py` / `tools.py`.

- **Satisfies Requirement 9 (which stages a request went through)**: LangSmith's trace view unfolds in tool-call order — routing decisions, each tool call (`search_documents` / `generate_chart` / `web_search` / the `generate_trend_prediction` added in 4.2), and every internal LLM call (reranking, evaluation scoring, etc.) are each recorded as an independent span, so a developer can see directly what steps a given question triggered.
- **Satisfies Requirement 10 (cost visibility)**: LangSmith records token usage per trace and converts it to cost; combined with project/time-range filtering, this gets you a cost summary for any time window without implementing billing logic yourself.
- **Satisfies Requirement 11 (traceable failures)**: failed/erroring spans in a trace are flagged, so a developer can directly locate whether a failure happened during retrieval, reranking, generation, or prediction confirmation, with no extra instrumentation needed.

**Scope of change**: almost non-invasive to existing code — just load the relevant environment variables at startup; `.env.example` gains three optional variables, `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY` / `LANGCHAIN_PROJECT` (leaving them unset turns observability off without affecting existing functionality, keeping it "lightweight and optional").

### 4.5 Conversation History Persistence

**Corresponds to**: PRD Requirements 12, 13; Goals P0 #5.

**Approach**: switch to LangGraph's `PostgresSaver` checkpointer, replacing the current model of "the client maintains history, and the last few turns are explicitly passed to `run_agent` on every request." `agent.py`'s `create_agent(...)` gets `checkpointer=PostgresSaver.from_conn_string(...)`; `run_agent` changes to being invoked by `thread_id` (`config={"configurable": {"thread_id": session_id}}`), with message history automatically maintained and continued by LangGraph — `api.py` no longer needs to assemble `conversation_history` into the request body.

**One reassuring fact worth confirming**: in the existing architecture, structured data like the chart's base64, `sources`, and `web_findings` has never actually entered the Agent's `messages` state — as the README's "Technical Challenges" section notes, this data is written into a per-request `capture` dictionary via closures, and the LLM side only ever sees a short text acknowledgment. This means that after switching to the checkpointer, **these large fields will not automatically get persisted into Postgres** — only the actual conversation text gets stored, with no extra filtering needed.

**Cross-device mechanism**: a conversation maps to a `session_id` (i.e. a `thread_id`). The first time a question comes in without a `session_id`, the backend generates one and returns it in the response; the frontend writes it into the URL's query parameters (not just localStorage), and the user can copy/bookmark that link to continue the same conversation on another device — no login required, consistent with the Non-Goal of not building an account system.

**Scope of change**:
- `api.py`: `AskRequest` gains an optional `session_id` field; the response carries the `session_id` used for that call.
- `agent.py`: `run_agent`'s signature changes from taking a `history` list to taking a `session_id`; the `messages = [dict(turn) for turn in (history or [])]` assembly logic is no longer needed.
- `ask.html`: reads/writes the `session_id` in the URL, and no longer needs to maintain and send a history array itself.
- New environment variable required (Supabase's direct Postgres connection string — a different credential from the existing `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`, which are REST API credentials). On first run, `checkpointer.setup()` needs to be run once to create the tables, the same kind of one-time setup step as the existing `match_documents.sql` / `keyword_search.sql`.

### 4.6 Adversarial Input Protection (Lightweight)

**Corresponds to**: PRD Requirements 14, 15; Goals P0 #6. Follows the previously stated direction of not wanting this to be heavy — the approach doesn't add an extra LLM classification call, only rule-based pre-filtering plus system-prompt hardening.

- **Input pre-filtering**: before a request reaches the Agent, run a lightweight match against a set of regex/keyword patterns (e.g. "ignore previous instructions" / "忽略之前的指令" / "what's your system prompt" / "roleplay as someone else" and other common solicitation templates). A match returns a fixed refusal directly, without ever entering the Agent — which also saves an unnecessary model call.
- **System-prompt hardening**: add an explicit behavioral rule to `agent.py`'s `SYSTEM_PROMPT` — never leak, restate, or discuss its own system prompt/internal instructions; and treat any content, whether from user input or retrieved material, that tries to make it change roles or skip its rules as ordinary text to be ignored, not as a new instruction. This covers both "a user directly soliciting it" and "a poisoned knowledge-base document indirectly injecting instructions," and corresponds to Requirement 15's "core behavioral guarantees must not be bypassable."
- **Boundary**: this only blocks "obvious" solicitation attempts (Requirement 14's original wording), and doesn't aim to defend against a carefully constructed jailbreak prompt — that's the already-established scope of "lightweight protection" (Non-Goal #1).

**How Success Metric #10 is satisfied**: run a set of common solicitation/behavior-deviation test cases (per PRD Open Question 9, these don't exist yet and need to be built) against this filter-plus-hardening setup, checking whether they're all correctly blocked and whether the core behavioral guarantees hold.

### 4.7 Web Search Quality Fix

**Corresponds to**: PRD Requirements 16, 17; Goals P0 #7. Scope continues within the boundary PRD Non-Goal #6 already set — doing the best achievable within the existing search source (Tavily), without bringing in a new provider.

**Specific fixes**:

1. **Tighten the time-window parameter**: the existing `TavilySearch(max_results=5, topic="news")` call has no time-range restriction on results. Add Tavily's supported recency time-window parameter to reduce the chance of stale content being returned in the first place, rather than filtering after the fact.
2. **Query rewriting**: for questions that hit a "timeliness signal" (routing rule 3), before passing the query to Tavily, explicitly append temporal intent to the query text (e.g. the current year, or "latest"), so the search itself is more likely to surface recent content rather than relying on the model to judge this after the fact.
3. **Honest fallback (corresponds to Requirement 17)**: even with the above adjustments, if a given search still returns entirely stale content (no result's publish date falls within a reasonable time window), the system must honestly say "no sufficiently recent information was found," rather than presenting stale results as current — this fallback behavior doesn't depend on whether the first two adjustments actually worked; it holds at all times.

**Acceptance approach**: corresponds to Success Metric #11 — web search results all carry a date, and the "honestly reports when nothing newer is found" behavior can be observed actually firing during testing (proving the fallback logic works, rather than being decorative).

## 5. Risks and Mitigations

| Risk | Description | Mitigation |
|---|---|---|
| The LangGraph checkpointer switch is a breaking interface change | `run_agent` changes from taking `history` to taking `session_id`; `api.py`/`ask.html` need to change in lockstep — this is an incompatible interface change | The project has no legacy user data to migrate (it's a demo), so the switch can happen directly without a compatibility transition layer |
| LangSmith is a third-party dependency | Call data (including the raw question text) gets sent to LangSmith — worth checking for sensitive content; the free tier has usage limits | Controlled by an environment-variable toggle, off by default; at higher volume, evaluate whether sampled rather than full reporting is needed |
| LLM-as-judge evaluation has its own bias | The judge model may favor longer or more "polished-looking" answers over genuinely more accurate ones | State this limitation explicitly in the evaluation report; don't treat evaluation scores as absolute truth; manually spot-check a sample of evaluated cases |
| The prediction-approval queue depends on timely human review | If you don't open the review page and process `pending` records in a timely way, users keep seeing "under review" | This is an operational-cadence issue, not a technical defect; the review page can show a simple "pending count" indicator to help you track it |
| The input pre-filter may misfire on legitimate questions | Rule matching might catch a legitimate question that merely discusses "what is prompt injection" | Rules only match "instruction-style" solicitation templates (e.g. "ignore previous instructions"), not questions that merely mention or discuss related terms; accepting a small number of edge-case false positives is a known cost of the lightweight approach |
| A session link is effectively an implicit access credential | 4.5's cross-device approach relies on a copyable `session_id` link with no identity binding — anyone who obtains that link (via a shared screenshot, browser history, an accidental forward) can read/continue that conversation | An acceptable tradeoff at the demo stage, but worth being explicit about: this link is effectively the "key" to a conversation and shouldn't be shared like an ordinary link; if this becomes a real concern later, it should pull forward the P1 multi-user auth goal rather than being patched within P0 |
| Combined risk of session-link + wide-open CORS + no auth | `/ask` is currently open to any origin with no identity check; combined with the session link above, a third-party script that obtains or guesses a `session_id` could in principle continue that conversation, and if it hits prediction keywords it could keep writing pending records into `trend_predictions`, flooding the review queue | Accepted at the P0 stage (low likelihood at demo scale); if mitigation is needed, simple rate-limiting per `session_id` is enough — a full auth system isn't required for this |
| Similarly-worded topics may be judged as "entirely new" | 4.2's topic matching relies on embedding similarity with no defined threshold value; semantically identical but differently-worded questions (e.g. "future trend of the price war" vs. "how will the NEV price war develop") may be misjudged as different topics, each generating its own pending record | The concrete similarity threshold needs tuning against real usage data — an implementation-stage todo (see appendix); the review page can offer a simple "similar title" grouping hint to reduce manual review cost |

## 6. Resolution of PRD Open Questions

| # | PRD Open Question | How this document handles it |
|---|---|---|
| 1 | The specific numeric target for "quality exceeds baseline" | Still undecided — needs the first round of evaluation from §4.3 to run before a number can be filled in; this design doesn't presume one |
| 2 | Quantifiable standard for web search timeliness | Partially resolved: §4.7 gives concrete adjustments (tighter time window + query rewriting), but follows the PRD's stance of not committing to a specific numeric threshold |
| 3 | Build order and timeline across P0/P1 goals | Not addressed — this is a project-management question, out of scope for a technical design |
| 4 | Who performs human confirmation, and how it's triggered | **Resolved** (§4.2): an asynchronous approval queue + a review page, operated by you |
| 5 | Timing for follow-on technical documents | Not applicable — this document is that "later technical document" |
| 6 | Baseline is not precisely defined | **Resolved** (§4.3): the same underlying model with retrieval stripped out (`gpt-4o-mini` answering directly) |
| 7 | Tension between human confirmation and live demos | **Resolved** (§4.2): asynchronous approval plus a naturally-growing approved-prediction library; only approved content is ever shown live |
| 8 | "Disagreement" has no operational definition | **Sidestepped rather than answered** (§4.1): no active detection is introduced; Requirement 2 is satisfied structurally by "internal and external results are always shown side by side, never merged" — this avoids the difficulty of defining "disagreement" in the first place; the concept of "what counts as a disagreement" is still undefined, it has simply become unnecessary to define |
| 9 | Solicitation test cases don't exist yet | Partially resolved: §4.6 identifies the need to build them, but the actual test cases remain a follow-up task, not a direct output of this document |
| 10 | How internal/external labeling and prediction labeling coexist | Partially resolved: §4.1 and §4.2 each define their own labeling rules, but how the two stack when an answer is both a prediction and a fusion of internal + external sources — the concrete visual treatment — is left to frontend design at implementation time |

## 7. Appendix

**Glossary**

- **thread_id / session_id**: the unique identifier for one continuous conversation; the LangGraph checkpointer uses this to associate historical messages with the same conversation.
- **checkpointer**: LangGraph's storage backend for persisting Agent state (including message history); this design uses `PostgresSaver`.
- **LLM-as-judge**: using an extra LLM call to score or compare candidate content, in place of human scoring — the core mechanism behind §4.3's evaluation approach.
- **Ablation**: comparing system behavior with and without a given component, one at a time, to verify that component's actual contribution.

**Files touched / added** (overview, not a final commit checklist)

- Changed: `agent.py` (routing rules, checkpointer integration, new tool registration, hardened system prompt), `tools.py` (`search_web` time window and query rewriting), `api.py` (`session_id` parameter, input pre-filtering), `ask.html` (`session_id` in the URL, prediction-label display).
- Added: the `generate_trend_prediction` tool implementation, the `trend_predictions` table's setup SQL (including the similarity query/RPC used for topic matching, distinct from the existing `match_documents`/`keyword_search`), the `review.html` review page and its API, and the evaluation scripts (eval set + metric computation + ablation batch runner).

**Still to be produced / decided at implementation time** (this document only defines requirements and methods; specific values and interface details are out of scope here)

- The concrete list of input-protection test cases (Open Question 9).
- The concrete list of evaluation questions (10-20 per topic, per §4.3).
- The concrete visual design for the dual prediction/fusion labeling in the interface (Open Question 10).
- The concrete similarity threshold for §4.2's topic matching (see the §5 risk table).
- Routing priority when the prediction-keyword rule and the timeliness rule both hit (e.g. "what will the future trend be" triggers both rules, and there's currently no defined precedence).
- The concrete request/response schema for the review page's approve/reject API.
