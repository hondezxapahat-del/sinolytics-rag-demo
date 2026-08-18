# Sinolytics RAG Demo — Technical Design v1.2

> This document is written against [PRD_v1.2.en.md](PRD_v1.2.en.md) and describes the technical design behind login, the conversation-history list, the year-fabrication fix, and language switching. Unlike the v1.1 tech spec (design first, then implementation), this document is a factual record of code that was already written and tested.

## 1. Background and Goals

Corresponds to PRD v1.2: v1.1 already handled conversation-history persistence (LangGraph `PostgresSaver` checkpointer, see [TechSpec_v1.1.en.md](TechSpec_v1.1.en.md) §4.5), but had no concept of an account and no way to list "everything I've asked." Separately, real-world testing surfaced a reproducible year-fabrication issue. Separately again, the product serves a "China desk" consulting firm whose users likely speak English as a first language, which calls for a switch that toggles both the interface and answer language together. This document records how all three were actually addressed.

## 2. Current State Analysis (after v1.1)

- Conversation identity relied entirely on a randomly generated `session_id` carried in the URL's query string — anyone holding that link could read and continue that conversation. TechSpec v1.1 §5's risk table already flagged this ("a session link is effectively an implicit access credential") but left it as an accepted, unresolved risk at the time.
- There was no concept of "who owns this `session_id`," so there was no way to list "all conversations a given user created."
- `/ask` had no identity check at all — anyone could call it directly.
- Answers would occasionally state a specific year that doesn't appear in the source material (e.g. the source literally says "2026" and the answer says "as of 2024") — the root cause was that the existing prompts only forbade "padding in background information beyond the source material," with no rule specifically targeting "fabricating a year/date," which reads like phrasing but is actually fabricating a fact.
- The interface only ever had one language, hardcoded into the HTML, with no switching mechanism. The AI's answer language followed whatever language the question was asked in, with no independent concept of "current interface language" and nothing in the code that could override it.

## 3. Overall Architecture

Two new tables:
- `users`: accounts (username + hashed password).
- `conversation_threads`: a lightweight ownership/title index for `session_id` values — it doesn't duplicate the actual conversation content (that still lives in the checkpointer's own tables), it only answers "who owns this session_id, what's its title, when was it last updated."

`/ask` now requires a login token; new endpoints were added: `/auth/signup`, `/auth/login`, `/conversations` (list), `/conversations/{id}/messages` (read one thread's history), and `/conversations/{id}` (delete, `DELETE` method).

```mermaid
flowchart TB
    subgraph Client[Frontend]
        LOGIN[login.html]
        SIDEBAR[ask.html sidebar]
    end

    subgraph API[api.py]
        AUTH[/auth/signup, /auth/login/]
        DEP[Auth dependency<br/>parses the Authorization header]
        ASK[/ask]
        CONV[/conversations endpoints/]
    end

    subgraph Data[Supabase / Postgres]
        USERS[(users table)]
        THREADS[(conversation_threads table<br/>ownership + title index)]
        CHK[(checkpoint tables<br/>actual conversation content, from v1.1)]
    end

    LOGIN -->|username+password| AUTH
    AUTH --> USERS
    AUTH -->|issues token| LOGIN

    SIDEBAR -->|requests with token| DEP
    DEP -->|passes| CONV
    DEP -->|passes| ASK

    ASK -->|check session_id ownership| THREADS
    ASK -->|create/update ownership record| THREADS
    ASK -->|read/write actual conversation| CHK

    CONV -->|list/delete| THREADS
    CONV -->|read one thread's text| CHK
```

Language switching needs no new tables and no new endpoints — it's purely a frontend text translation, plus one extra field on the `/ask` request body telling the backend which language to answer in this time. Details in §4.4.

## 4. Detailed Design

### 4.1 Account & Login

- Passwords are hashed with bcrypt before storage — no plaintext password ever appears in the database.
- On successful login, a token valid for 30 days is issued; the frontend stores it in browser local storage and attaches it to every subsequent request's header.
- There is no password-recovery/reset flow — a lost password means registering a new username. This is an explicit Non-Goal, consistent with the "lightweight login" positioning, not an oversight.

### 4.2 Conversation History List

- `conversation_threads` stores only "ownership + title" — the title is the first 60 characters of the conversation's first question (truncated beyond that).
- The list is ordered by last-updated time, most recent first.
- **Opening a past conversation** reads the raw message history directly from the checkpointer and reconstructs it as plain-text Q&A — since structured data like source citations, chart images, and prediction labels was never part of the checkpointed state to begin with (already explained in TechSpec v1.1 §4.5), an old conversation only shows text, not the original rich display. This is a known limitation, already listed under Out of Scope in PRD v1.2 — not an oversight in this round.
- Deleting a conversation removes both the index-table record and the checkpointer's actual data, leaving no orphaned data behind.
- **A meaningful security side benefit**: `/ask` now checks whether a given `session_id` was created by the currently logged-in account, and rejects it (403) if not — this incidentally resolves the "anyone with the link can read it" risk carried over from v1.1 (§2 above), with no separate fix needed.

### 4.3 Answer Honesty Fix (Years/Dates)

Three places were changed at once, because each is an independent path that can generate user-facing text on its own — fixing only one would leave the other two open:

1. **The internal-retrieval answer-generation prompt** — an explicit rule was added: "only state a year that literally appears in the source material; if the source doesn't state one, don't add one yourself."
2. **The acknowledgment prompt returned to the Agent by the web search tool** — at this step the Agent was never told the actual dates of the results to begin with (only "N results were found"), so it's now explicitly told "you don't know the specific dates of these results, so your acknowledgment must not state any year."
3. **The system prompt's general rule set** — the same rule was added here too, to govern the final synthesized answer, not just the two tool-related paths above.

This class of problem is fundamentally probabilistic model behavior — a prompt change doesn't mean "will never happen again," only "meaningfully less likely." Repeatedly re-testing the exact questions that previously reproduced the issue no longer produced a fabricated year, but this hasn't been validated at any statistically meaningful scale, and doing so isn't planned (per the PRD Non-Goals: this isn't a systematic hallucination audit).

### 4.4 Language Switching

The design deliberately stays lightweight: no frontend framework or i18n library — just a plain frontend lookup dictionary plus one request parameter covers both halves of the requirement (interface text, AI answer language).

**Interface text (frontend only, no backend involvement)**

- New `i18n.js`: a JS object mapping each translatable phrase to a key holding `{ en: "...", zh: "..." }`.
- HTML elements that need translating carry a `data-i18n="key"` marker; switching languages walks the page and replaces each marked element's text with the dictionary entry for the selected language.
- `index.html`, `login.html`, and `ask.html` all wire into this mechanism; `review.html` is excluded per the PRD and left untouched.
- The language toggle sits in the top corner of every page, alongside the login-status button — a simple text toggle ("EN / 中"), no dropdown.
- The selection is stored in the browser's `localStorage` (matching the PRD requirement to remember it per-device, not per-account — it was never going to touch the database anyway). Defaults to English when nothing is stored yet.

**AI answer language (frontend + backend)**

- `AskRequest` gets a new `language` field (`"en"` or `"zh"`); the frontend sends the currently selected value with every question.
- `run_agent()` uses this parameter to append an instruction to that call's system prompt: "answer in {language} this time, regardless of what language the question was asked in" — overriding the default "match the question's language" behavior.
- This instruction is independent of, and doesn't conflict with, the existing "never fabricate years/dates" rules — one governs what language to write in, the other governs whether the content is grounded; both apply at once.
- The instruction isn't an absolute mandate: the prompt also adds "unless the user explicitly asks for a different language or a mixed-language answer in this specific question, follow the language above" — matching the exception carved out in PRD Requirement 14. In other words, Chinese/English mixing on its own is still an undesired failure mode (see the §5 risk table); an explicit user request is the one deliberately designed exception, not the same thing as that failure mode.
- The internal acknowledgment prompt the `web_search` tool hands back to the Agent (e.g. the "no results found" note) does not need to be translated — that text is an internal instruction meant for the model, not the final text shown to the user. What the user actually sees is the model's own synthesized answer, composed according to the current language instruction.

**Fixed system messages**

- `DAILY_LIMIT_MESSAGE` (daily quota exhausted) and `REFUSAL_MESSAGE` (suspicious-input refusal) both change from a single English string to an `{en, zh}` dictionary, selected using the request's `language` field.
- Login/signup error messages (e.g. "incorrect username or password") are **not** localized — a deliberate lightweight tradeoff: those two requests happen before any language selection is passed to the backend, making this meaningfully more work to wire up, and the actual trigger frequency is low enough that it isn't worth the cost.

**Unaffected**

- Saved conversation history is left completely alone — an old record keeps whatever language it was generated in and is never retroactively translated just because the interface language was switched later (explicitly excluded in the PRD).

## 5. Risks and Mitigations

| Risk | Description | Mitigation |
|---|---|---|
| The year-fabrication fix reduces probability, it doesn't eliminate the problem | Prompt-level constraints can only meaningfully reduce an LLM's probabilistic behavior, not guarantee it away | Explicitly stated in the PRD Non-Goals that this isn't a systematic audit; if it recurs, it needs to be logged and handled separately — it should never be assumed "solved" |
| Login tokens are long-lived (30 days) with no active revocation mechanism | Once issued, a token can't be individually revoked before it expires (e.g. logging in on a new device doesn't invalidate the old device's token) | Limited impact for a personal demo project; genuine public exposure later would need a token blocklist or a shorter lifetime plus a refresh mechanism — out of scope for now |
| History-list titles are just the first 60 characters of the first question | If the first question is very long or generic (e.g. "hi"), the list title may not be distinctive enough | An accepted simplification that doesn't affect core functionality; revisit with smarter title generation only if this becomes a real usability problem |
| The AI answer-language instruction is a prompt-level constraint, same as the year-fabrication fix | "Answer in language X" is equally probabilistic and can't be guaranteed at 100% — in theory, Chinese/English mixing could still occur | Same tradeoff as §4.3: repeated testing didn't reproduce it, but this is not a mathematical guarantee; a real recurrence needs to be logged and handled on its own |
| Login/signup error messages aren't localized | Every other piece of text on those two pages follows the language switch except the error messages, which stay in English | Already stated in this section and the PRD as a deliberate lightweight tradeoff, not an oversight — the trigger frequency (wrong username/password, etc.) is low enough that the impact is limited |

## 6. Resolution of PRD Open Questions

| # | PRD Open Question | How this document handles it |
|---|---|---|
| 1 | How long a login session should last, and what the experience should be once it expires | A default has been picked (30 days), but no dedicated "what happens when it expires" experience was designed — it currently just passively redirects to the login page |
| 2 | Whether to fix "history view is plain-text only, missing the original rich display" in the future | Not addressed here — the PRD already lists this under Out of Scope. If pursued later, the core decision is whether to persist more structured content into history at all, which would change the deliberate "text only, no large fields" tradeoff made in TechSpec v1.1 §4.5, and needs its own separate evaluation |

## 7. Appendix

**Files touched / added**

- Added: `auth.py` (password hashing, token issuance/verification), `login.html`, `auth_and_threads.sql` (`users`/`conversation_threads` table setup), `i18n.js` (the Chinese/English dictionary and toggle logic).
- Changed: `api.py` (auth endpoints, `/conversations` endpoints, `/ask` now checks identity and thread ownership, `AskRequest` gains a `language` field, `DAILY_LIMIT_MESSAGE`/`REFUSAL_MESSAGE` are now bilingual), `ask.html` (sidebar, logout button, requests now carry the token, wired into `i18n.js`, language toggle button), `index.html` / `login.html` (login-status entry point in the top corner, wired into `i18n.js`, language toggle button), `tools.py` / `agent.py` (prompt adjustments for year/date honesty, plus the `language`-driven answer-language instruction).

**Still to be produced / decided at implementation time**

- The concrete user experience once a token expires (whether a prompt message, auto-refresh, etc. is needed).
- Large-scale statistical validation of the year-fabrication fix (if stronger confidence is needed later, this could be folded into §4.3's evaluation question set as a dedicated test-case category).
- The exact set of keys/strings `i18n.js` needs to cover — left to be filled in during implementation rather than enumerated up front at the design stage.
