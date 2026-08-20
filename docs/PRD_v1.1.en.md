# Sinolume RAG Demo — PRD v1.1

## Background

v1.0 is a RAG-based Q&A demo focused on China tech-policy and industry briefings: it can answer questions grounded in an internal knowledge base (Sinolytics export-controls whitepaper and NEV price-war content, two topics), generate an NEV price-trend chart, and query the web for real-time information when needed, while carrying multi-turn conversation context. The project was originally built as a technical proof-of-concept for the Sinolytics "Working Student – Data and AI Application" role, intended to demonstrate production-shaped retrieval Q&A, tool-use, and lightweight data visualization capability.

This is the starting point v1.1 iterates on.

## Problem Statement

The core risk facing this product right now is that the standard for "what counts as a good answer" has never been clearly defined — and that standard directly determines whether the product has a reason to exist.

Measured against a general-purpose LLM's (e.g. ChatGPT) standard of "comprehensive, web-wide coverage," the product currently falls short — but that may be the wrong yardstick to begin with. The product's real value should come from fusing "deep analysis from the company's proprietary industry reports" with "real-time external information," with sources clearly distinguished — not from competing head-on with a general-purpose LLM's web-wide breadth. Until that positioning is explicitly settled, there's no way to tell whether the current experience gap versus ChatGPT is a real problem worth fixing or simply the wrong comparison — and therefore no way to demonstrate the product is worth using at all.

This positioning risk shows up concretely as the following unresolved gaps:

- **Internal retrieval and web search are disconnected**: internal document retrieval results and web search results are currently displayed separately, with none of the incremental value that fusing the two should provide — and that fusion is exactly where the real differentiation from a general-purpose LLM should come from.
- **Weak web search result quality**: the connected search API returns noticeably stale news, undermining the credibility of "latest/trend" questions and the timeliness value the external-information side is supposed to provide.
- **No way to quantify answer quality**: there is currently no metric or data backing the claim that "this system is reliable," whether for internal document Q&A or for trend prediction — it can only be judged subjectively.
- **Runtime status and cost are invisible**: it's unclear how many model calls a given question triggers or how much it costs, and when something goes wrong it's hard to tell whether retrieval, reranking, or generation is at fault.
- **Conversation history doesn't persist**: refreshing the page or switching devices loses prior conversation history — the experience feels closer to a one-off demo than an actual product.
- **No protection against adversarial input**: the question box is exposed to any visitor with no mechanism to prevent prompt extraction, system-prompt leakage, or instructions designed to make the system deviate from its intended behavior.

## Goals & Non-Goals

### Goals (P0 — must ship in v1.1, directly serves the "moat / positioning" thread)

1. Position the product as an "internal + external fused vertical assistant": external web results and internal industry-report analysis must be clearly labeled by source and presented separately, never conflated.
2. Add an "internal-analyst-style" trend prediction capability; predictions must pass a human confirmation step before being shown to users.
3. Answer quality must be quantifiably verifiable, not judged by subjective impression alone.
4. Runtime status and per-query cost must be visible.
5. Conversation history must persist.
6. Provide protection against adversarial external input (prompt extraction, system-prompt leakage, instructions designed to make the system deviate from its intended behavior).
7. Resolve the problem of noticeably stale web search results.

### Goals (P1 — do if time allows, carried over from the README's original Future Directions list)

8. Multimodal document parsing (PDF, tables, scanned documents).
9. Additional chart topics/datasets, beyond the current single NEV price-war chart.
10. Integration with external BI tooling, so visualization output can plug into a broader dashboard ecosystem.
11. Multi-user authentication and rate limiting.

### Non-Goals

1. Not building a full production system for anonymous public users — even if P1's auth/rate-limiting ships, it's lightweight protection only, not an enterprise-grade permissions system.
2. Not aiming for fully automated, unreviewed publication of AI-generated trend predictions — the human confirmation step is a hard requirement; there is no "skip human review" mode.
3. Not expanding the breadth of knowledge-base topics (no new industry-topic documents added) — v1.1 focuses on making the existing corpus solid.
4. Not migrating or replacing the technology stack — v1.1 is an incremental improvement on the existing system, not a re-platforming effort.
5. Not building multi-person collaboration or a shared conversation thread — persisted conversation history remains a single-user memory, not something multiple people co-edit.
6. Not committing to web search timeliness fully matching ChatGPT's web version — if the staleness problem turns out to be a limitation of the underlying data source itself, v1.1 only guarantees "the best achievable given the current information source," without an open-ended commitment.

## Requirements

### Product Positioning / Internal-External Source Separation

1. For a given topic, the product must be able to present both "what the internal industry report says" and "what the latest external web information says" at once, with sources clearly labeled and never merged into one undifferentiated block.
2. When internal and external information disagree or conflict on the same topic, that disagreement must be faithfully presented — not reconciled into a single unified statement.

### Trend Prediction + Human Confirmation

3. The system must be able to generate a simple trend prediction for a given topic, based on the analytical style evident in the internal analysts' past reports.
4. A trend prediction must pass an explicit human confirmation step before being shown to a user; unconfirmed predictions must never be shown directly.
5. The interface must clearly distinguish "a human-confirmed prediction" from "a directly retrieved answer," so users don't treat the two as equally authoritative.

### Quantifiable Answer-Quality Verification

6. The product must have a repeatable evaluation method covering every topic currently in the corpus (Chinese AI model pricing/market dynamics, China's desktop AI office-agent market, China's industrial robot installations, export controls) — not a one-off manual judgment.
7. The evaluation must be able to compare the product's answers against "a general-purpose LLM baseline without retrieval augmentation," in order to demonstrate the product outperforms that baseline in this vertical (the specific evaluation methodology is left to a later technical document).
8. There must be a clear, explainable bar for what counts as an acceptable answer, not just an abstract score.

### Runtime Status and Cost Visibility (developer/back-office view, not user-facing)

9. Developers need to be able to see what actually happened behind any given question.
10. Developers need to be able to see the approximate cost incurred by any given question.
11. When a request fails or produces a poor-quality answer, developers need to be able to trace the failure to a specific stage — retrieval, reranking, generation, or prediction confirmation.

### Conversation History Persistence

12. Users switching devices or refreshing the page should be able to continue seeing prior conversation content.
13. Users need to be able to look back at questions asked earlier, not just within the current page session.

### Adversarial Input Protection (lightweight)

14. The product must have baseline protection able to recognize and reject clearly identifiable attempts to extract the system prompt or induce the system to deviate from its intended behavior.
15. Even under adversarial input, core behavioral guarantees — such as "external results must be source-labeled" and "answers must be grounded only in retrieved material" — must not be bypassable.

### Web Search Quality

16. The product must be able to surface web information that is genuinely current, not obviously stale content.
17. When a given search genuinely turns up nothing newer, the system must honestly say so ("no newer information found") rather than passing off old information as current.

## Success Metrics

1. **Source separation**: On a random sample of questions spanning internal and external information, manual review confirms answers clearly distinguish "internal report findings" from "external web information," with no cases of source conflation.
2. **Disagreement surfaced**: In sampled review, cases where internal and external conclusions diverge are faithfully presented as a disagreement, not silently reconciled into a single conclusion.
3. **Predictions are human-confirmed**: Every trend prediction shown to users can be traced back to an explicit human confirmation record; no unconfirmed prediction is ever shown directly.
4. **Predictions are distinguishable**: An uninformed reader (e.g. an interviewer) can, from the interface alone, correctly tell "a human-confirmed prediction" apart from "a directly retrieved answer."
5. **Evaluation coverage**: An evaluation set has been built covering every topic currently in the corpus (Chinese AI model pricing/market dynamics, China's desktop AI office-agent market, China's industrial robot installations, export controls), and comparison results between the product and "a non-retrieval general-purpose LLM baseline" have been produced.
6. **Quality exceeds baseline**: Evaluation results show the product's answer quality is at or above baseline on most evaluated questions (the exact numeric target is TBD pending the first evaluation run — see Open Questions).
7. **Runtime traceability**: For any failed or poor-quality request, a developer can, after the fact, trace the issue to a specific stage — retrieval, reranking, generation, or prediction confirmation.
8. **Cost visibility**: Developers can retrieve call-cost data for any time window; there is no scenario where the cost incurred is simply unknown.
9. **Conversation history intact**: After switching devices or refreshing the page, prior conversation history is fully retained with nothing lost.
10. **Input protection effective**: Against a set of common prompt-extraction / behavior-deviation attempts, the system neither leaks its system prompt nor can be induced to violate its core behavioral guarantees.
11. **Search timeliness**: Web search results carry a date, and when no newer information is found the system says so honestly rather than presenting stale content as current.

## Out of Scope

- If P1 goals (multimodal parsing, additional chart topics, BI integration, multi-user auth/rate-limiting) aren't completed in v1.1 due to time constraints, they roll over to v1.2 and beyond — this doesn't count against v1.1 acceptance, but P1 work also must not slow down P0 delivery.
- The specific design of the evaluation methodology (how the evaluation set is constructed, whether ablation studies are needed, etc.) is out of scope for this PRD and is left to a later technical document.
- Any capability not explicitly listed in this document's Goals/Requirements is, by default, considered out of scope for v1.1.

## Open Questions

1. The exact numeric target for "quality exceeds baseline" (e.g. win rate, score gap) is undecided, pending the first round of evaluation data.
2. On web search timeliness, the product currently only commits to "the best achievable given the current information source," with no quantifiable timeliness standard — should a concrete threshold be set later?
3. The specific build order and timeline across the seven P0 goals and four P1 goals hasn't been scheduled.
4. Who performs the human confirmation step, and how it gets triggered, is still undefined — only the requirement that this step must exist has been established; the owner and workflow are left to later discussion or a technical document.
5. The timing for follow-on technical documents (evaluation methodology, ablation study design, the concrete design for internal/external fusion display, etc.) hasn't been set.
6. "Baseline" is not precisely defined in this document — does it mean "the same underlying model with retrieval stripped out," or literally ChatGPT? This needs to be settled before the evaluation (Requirement #7) has a well-defined comparison target.
7. There's an unresolved tension between the human-confirmation step and live demos: Requirement #4 requires predictions to pass human confirmation before being shown to a user, but Success Metric #4 envisions an interviewer seeing a prediction live in the interface. If an interviewer asks an arbitrary question on the spot, who performs that confirmation, and when? This workflow gap directly affects whether Requirement #3 ("generate a simple trend prediction for a given topic") is actually feasible in a live-demo setting.
8. Requirement #2 requires internal/external disagreements to be "faithfully presented," but "disagreement" has no operational definition (how much divergence counts as a disagreement?); Success Metric #2 currently relies on ad hoc manual sampling, without a clearer standard.
9. The test cases referenced by Success Metric #10 (common prompt-extraction / behavior-deviation attempts) don't exist yet and need to be built before that metric can be verified.
10. Requirements #1–2 (internal/external source labeling) and Requirement #5 (prediction vs. retrieved-answer distinguishability) are two independent labeling schemes, and the document doesn't specify how they coexist: for an answer that is both a prediction and a fusion of internal + external information, how many layers of labeling does the interface need to show at once? This is the presentation layer for the product's core value proposition and is worth resolving early in later design work.
