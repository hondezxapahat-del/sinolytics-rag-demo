# Sinolytics RAG Demo — PRD v1.2

## Background

v1.1 (see [PRD_v1.1.en.md](PRD_v1.1.en.md)) has shipped: internal/external fusion display (found to already exist in v1.0, no new development needed), the trend-prediction + human-confirmation workflow, the evaluation methodology, runtime observability, conversation history persistence, adversarial input protection, and the web search quality fix.

Turning v1.1's design into real code, and actually testing it, surfaced four things that motivated this v1.2:

1. v1.1 solved "conversation history doesn't disappear on refresh or device switch," but not the further need of "let me look back at everything I've asked and manage those records" — that requires introducing the concept of an account, which was outside v1.1's original scope.
2. Real-world testing surfaced a reproducible issue: the system would occasionally invent a specific year in an answer that appears nowhere in the source material (e.g. the source literally says "2026" and the answer says "as of 2024"). This isn't high-frequency, but it directly violates the "never fabricate" principle this whole project has been built around — even a single wrong year is enough to make someone doubt the credibility of the entire answer.
3. This is a consulting firm built around a "China desk" — its users (e.g. interviewers) are likely to be English-speaking, so the product should default to a fluent English experience while still fully serving Chinese-speaking users. That calls for a single switch that toggles both the interface language and the answer language together.
4. Real-world testing also surfaced this: on content-rich documents (e.g. the export-controls whitepaper), answers read as generic — not wrong, just not making use of the specific numbers, organizations, or provisions actually present in the source. The root cause was that retrieval always fed a fixed, small number of chunks into the answer prompt regardless of how much of a document was genuinely relevant — the richer the topic, the more it got shortchanged. This connects directly to PRD_v1.1 Requirement 7's original promise to "prove this product beats a non-retrieval general-purpose LLM baseline in this vertical" — a generic answer can't carry that promise, so strictly speaking this isn't a new feature, it's a P0 commitment that wasn't actually being met.

v1.2 addresses all four.

## Problem Statement

**Conversation history is still "disposable."** v1.1 solved "does it survive a refresh," but users still have no way to look back at what they've asked or clean up records they no longer need — the only way to recover a conversation is remembering its specific link, and losing that link means losing the conversation. That's still a meaningful gap from what a real product should feel like — it reads more like a pile of independent, throwaway sessions than something with a manageable usage history.

v1.1's technical design also flagged an unresolved risk: a conversation link is readable by anyone who has it, with no real identity check behind it. That risk and "can't see my own history list" share the same root cause — the system has no concept of an account at all.

**Occasional year fabrication strikes directly at this product's core selling point.** Since PRD v1.1, this project has repeatedly emphasized "prove this is more trustworthy than a general-purpose LLM — never pad an answer with fabricated content beyond what the source material contains." Inventing a year that isn't in the source material is a direct counterexample to exactly that principle — and it's a particularly dangerous kind of error, because it reads completely naturally and isn't the sort of thing a user would catch on common sense alone. If it surfaces in a real setting (e.g. an interview demo) and gets questioned, it undermines trust in the whole system being "reliable," not just that one answer.

**Generic answers strike at the other half of the same selling point.** Year fabrication is "saying something it shouldn't (inventing)"; generic answers are "not saying something it should (failing to use information the source actually contains)" — both erode the same core claim that this product understands the vertical better than a general-purpose LLM. PRD_v1.1 Requirement 7 explicitly requires the evaluation to prove this product beats a non-retrieval baseline — if the answers themselves are generic enough to carry no real substance, that evaluation produces a number without meaning.

## Goals & Non-Goals

### Goals (P0)

1. Add lightweight username+password login — originally a "do if time allows" P1 item in v1.1, pulled forward now because the conversation history list can't work without an account. Scope stays narrow: just "log in, own your history" — no roles, no password recovery, no email verification.
2. Once logged in, users can see a history list belonging only to their own account — browsable, switchable, deletable.
3. Eliminate the class of problem where the answer fabricates a specific year/date that isn't in the source material — this applies to text generated at any stage (tool acknowledgments, the final synthesized answer, etc.), all of which must follow "no grounding, no date."
4. Users can switch the whole product's language (English/Chinese) from the interface; once switched, both the interface text and the AI's answer language follow that choice.
5. On content-rich documents, answers need to make use of the specific numbers, organizations, or provisions actually present in the source — not the same degree of generic summary regardless of how much material a document actually contains.

### Non-Goals

1. No enterprise-grade account system — consistent with v1.1's restraint: no roles, no password-recovery email, no multi-tenant isolation.
2. No multi-person collaboration or shared conversations — history remains each account's own memory, not something multiple people co-edit on the same thread.
3. Not revisiting or changing anything else v1.1 already settled (evaluation methodology, the prediction human-confirmation workflow, observability, etc.) — v1.2 only covers the two items in this document.
4. Not a systematic hunt to eliminate every kind of model hallucination — only tightens the rules for the specific, empirically-observed failure mode of fabricating years/dates. This does not mean hallucination in general has been "solved."
5. No support for any third language beyond English and Chinese.
6. No translation/retroactive conversion of saved conversation history — saved records keep the language they were generated in.
7. The language preference is not tied to the account in the database — it's remembered only on the local device/browser, so a new device/browser requires choosing again.
8. Not optimized for a large increase in corpus size — the current corpus is small (4 topics), and this fix hasn't been validated at a corpus scale far beyond the current one.

## Requirements

### Account & Login

1. Users need to be able to create an account (username + password) and log in.
2. The Q&A feature must not be usable while logged out — login is required first.

### Conversation History List

3. A logged-in user needs to see a history list belonging only to their own account, where each entry is identifiable by topic — not just a meaningless ID string.
4. Users need to be able to switch directly into a past conversation from the list and see what was asked and discussed at the time.
5. Users need to be able to delete a conversation from their own history.
6. One account must never be able to see, access, or delete another account's conversations — including via a direct link to that conversation.

### Answer Honesty (Years/Dates)

7. Any specific year or date stated in an answer must be traceable to the cited material or search results; if the source material doesn't state a year, the answer must not invent one.
8. This requirement must hold across every stage that generates user-facing text — not enforced in just one place while others are missed.

### Language Switching

9. There must be a clearly visible, easy-to-use language switch control in the interface.
10. The default language is English.
11. After switching, every piece of visible interface text (buttons, headings, prompts, etc.) must change to the selected language.
12. After switching, the AI answers questions in the currently selected language, regardless of what language the user's question was asked in.
13. The language selection is remembered until the user manually changes it back; a new device or browser requires choosing again.
14. A single AI answer must never mix Chinese and English, unless the user explicitly asks for a mixed-language answer.
15. Saved conversation history keeps the language it was generated in — it is not retroactively translated just because the interface language was later switched.
16. review.html (the internal review page) does not need to support this language switch.

### Answer Specificity

17. Answers should preferentially cite the specific numbers, dates, and organization/company names actually present in the source material, instead of using vague words ("various", "several", "significant") to summarize information the source could have stated concretely.
18. The number of reference chunks included in an answer needs to follow however many chunks actually clear the relevance bar — not a fixed small number regardless of how much of a document is genuinely relevant or how many relevant chunks were actually retrieved.
19. After generating an answer, a self-check pass is needed that reviews whether specific information from the source got replaced with vague wording, or whether clearly relevant source content was omitted — and corrects the answer before it's returned if either applies.

## Success Metrics

1. **Account isolation holds**: testing with two separate accounts confirms neither can see or reach the other's conversation history, even with a direct link to a specific conversation.
2. **History list works**: conversations can be created, switched to, and deleted normally, and what the list shows matches the actual conversation content.
3. **Year fabrication is substantially reduced**: re-running the specific questions that previously reproduced this issue, multiple times, no longer produces a year not present in the source material.
4. **English experience is fluent end to end**: operating entirely in English (login, asking questions, viewing history) never surfaces leftover Chinese interface text.
5. **Chinese experience is equally complete**: after switching to Chinese, the same end-to-end operation never surfaces leftover English text.
6. **Answer language responds correctly**: after switching languages, the AI's answer language follows the rule in Requirement 12.
7. **No language mixing**: repeated testing shows the AI's answers never mix Chinese and English, except when the user explicitly asks for a mixed-language answer.
8. **Noticeably more specific answers**: comparing before/after on the specific questions that previously reproduced the "generic answer" problem (e.g. export-controls-whitepaper-related questions), the post-fix answer visibly uses concrete numbers/organizations/provisions actually present in the source, instead of a vague summary.
9. **Evaluation confirms the baseline is still beaten**: re-running the evaluation PRD_v1.1 Requirement 7 already established (this product vs. a non-retrieval general-purpose LLM baseline) confirms this product's answer quality is still at or above baseline on most questions — this evaluation already existed as of v1.1; v1.2 just re-runs it to confirm the fix didn't regress it.

## Out of Scope

- Forgot-password / password-recovery flow.
- Email verification for accounts.
- Team/organization accounts or shared conversations across multiple people.
- Opening an old conversation from the history list only shows the plain text Q&A from that time — not the original source citations, chart images, or prediction labels. This is a known limitation of v1.1's persistence design; v1.2 does not address it, and whether to fix it later is left open.
- Support for any third language beyond English and Chinese.
- Translation/retroactive conversion of saved conversation history.
- Cross-device sync of the language preference (a new device requires choosing again).
- Retrieval optimization for a corpus scaled far beyond the current 4 topics — out of scope for this fix.

## Open Questions

1. How long a login session should last (a default has been picked, but not deliberated) and what the experience should be once it expires haven't been worked out in detail.
2. Whether to fix "history view is plain-text only, missing the original rich display" in a future version — doing so would raise the question of whether to persist more structured content into history at all, which is itself a real design decision left for later discussion.
