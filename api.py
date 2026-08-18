"""FastAPI layer for the Sinolytics agent: exposes POST /ask, wiring each
request into the LangChain agent (agent.py) that routes between document
search, chart generation, and web search."""

import re
import uuid
from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from agent import delete_conversation, get_conversation_messages, run_agent
from auth import AuthError, authenticate_user, create_access_token, create_user, decode_access_token
from retrieval import supabase
from tools import list_pending_predictions, review_prediction

app = FastAPI(title="Docs Q&A Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lightweight username+password login (PRD_v1.1.md Goal 8) — just enough to
# own a conversation history, see auth.py.
_bearer = HTTPBearer()


def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> int:
    try:
        return decode_access_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


class SignupRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@app.post("/auth/signup", response_model=TokenResponse)
def signup(request: SignupRequest):
    try:
        user = create_user(request.username, request.password)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return TokenResponse(access_token=create_access_token(user["id"]))


@app.post("/auth/login", response_model=TokenResponse)
def login(request: LoginRequest):
    try:
        user = authenticate_user(request.username, request.password)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    return TokenResponse(access_token=create_access_token(user["id"]))


# Thin ownership/title index on top of the checkpointer's own tables — see
# auth_and_threads.sql. Not exposed as endpoints directly; /ask and the
# /conversations routes below use these.
def _get_thread_owner(session_id):
    result = (
        supabase.table("conversation_threads")
        .select("user_id")
        .eq("session_id", session_id)
        .execute()
    )
    return result.data[0]["user_id"] if result.data else None


def _touch_thread(session_id, user_id, first_question):
    if _get_thread_owner(session_id) is None:
        title = first_question[:60] + ("…" if len(first_question) > 60 else "")
        supabase.table("conversation_threads").insert(
            {"session_id": session_id, "user_id": user_id, "title": title}
        ).execute()
    else:
        supabase.table("conversation_threads").update(
            {"updated_at": datetime.now(timezone.utc).isoformat()}
        ).eq("session_id", session_id).execute()


# Global (not per-account) daily cap on real /ask calls — a deliberately
# simple guardrail against the shared demo running up API costs, whether
# from someone signing up just to poke at it or heavier-than-expected
# legitimate use. Not exact under concurrent requests (check-then-write,
# no locking) — acceptable for this project's actual traffic level.
DAILY_ASK_LIMIT = 100
DAILY_LIMIT_MESSAGE = (
    "This demo has reached its shared daily usage limit. Please try again tomorrow."
)


def _try_consume_daily_quota(limit=DAILY_ASK_LIMIT):
    """Returns True and records the call if today's count is under the
    limit; returns False (without recording) if the limit is already hit."""
    today = date.today().isoformat()
    result = supabase.table("daily_usage").select("count").eq("usage_date", today).execute()
    current = result.data[0]["count"] if result.data else 0
    if current >= limit:
        return False
    if result.data:
        supabase.table("daily_usage").update({"count": current + 1}).eq("usage_date", today).execute()
    else:
        supabase.table("daily_usage").insert({"usage_date": today, "count": 1}).execute()
    return True


class ConversationSummary(BaseModel):
    session_id: str
    title: str
    updated_at: str


class ConversationMessage(BaseModel):
    role: str
    content: str


@app.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(user_id: int = Depends(get_current_user_id)):
    result = (
        supabase.table("conversation_threads")
        .select("session_id, title, updated_at")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    return result.data


@app.get("/conversations/{session_id}/messages", response_model=list[ConversationMessage])
def get_conversation(session_id: str, user_id: int = Depends(get_current_user_id)):
    if _get_thread_owner(session_id) != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return get_conversation_messages(session_id)


@app.delete("/conversations/{session_id}")
def delete_conversation_endpoint(session_id: str, user_id: int = Depends(get_current_user_id)):
    if _get_thread_owner(session_id) != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    supabase.table("conversation_threads").delete().eq("session_id", session_id).execute()
    delete_conversation(session_id)
    return {"status": "ok"}


# Lightweight pre-filter for obvious prompt-injection/solicitation attempts
# (see docs/TechSpec_v1.1.md §4.6). Deliberately narrow — only matches
# instruction-style phrasing, not questions that merely discuss these terms
# (e.g. "what is prompt injection?" should NOT be blocked). Not intended to
# stop a determined jailbreak attempt, only the obvious cases.
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+|any\s+)?(the\s+)?(above|prior|previous)\s+instructions", re.I),
    re.compile(r"disregard\s+(your|the|all)\s+(instructions|rules|guidelines)", re.I),
    re.compile(r"(reveal|show|print|repeat|what\s+is)\s+your\s+(system\s+prompt|instructions)", re.I),
    re.compile(r"你的?(系统)?提示词是什么"),
    re.compile(r"忽略(之前|上面|以上)(的)?(所有)?(指令|规则|提示)"),
    re.compile(r"(扮演|模拟|假装你是)(另一个|一个新的)?(角色|ai|助手)", re.I),
    re.compile(r"act\s+as\s+(a\s+)?(different|new)\s+(ai|assistant|character)", re.I),
    re.compile(r"you\s+are\s+now\s+(a|an)\s", re.I),
    re.compile(r"developer\s+mode", re.I),
]

REFUSAL_MESSAGE = "Sorry, I can't help with that request."


def _looks_like_injection_attempt(text):
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)


class AskRequest(BaseModel):
    question: str
    match_count: int = 3
    # Identifies the conversation thread (docs/TechSpec_v1.1.md §4.5). Omit
    # on the first turn — the server generates one and returns it; send the
    # same value back on every follow-up turn to keep history connected.
    session_id: str | None = None


class Source(BaseModel):
    content: str
    relevance_score: float


class WebFinding(BaseModel):
    content: str
    source: str
    url: str = ""
    date: str | None = None  # None means Tavily didn't provide one — never guessed


class AskResponse(BaseModel):
    answer: str
    session_id: str  # echo back so the client can persist/reuse it
    source_type: str = "internal"  # "internal" or "web"
    expert_note: str = ""  # only non-empty when retrieval relevance cleared the threshold
    sources: list[Source] = []
    chart_path: str | None = None
    chart_image: str | None = None  # raw base64, no data-URI prefix
    web_findings: list[WebFinding] | None = None  # populated on the web_search path
    internal_analysis: str | None = None  # only when internal KB was also genuinely relevant
    # populated on the generate_trend_prediction path (docs/TechSpec_v1.1.md §4.2)
    prediction_status: str | None = None  # "approved" or "pending"
    prediction_content: str | None = None  # only set when prediction_status == "approved"
    prediction_fallback: str | None = None  # regular internal analysis shown while pending


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest, user_id: int = Depends(get_current_user_id)):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question 不能为空")

    session_id = request.session_id or uuid.uuid4().hex

    # Requiring a real account closes a gap flagged in TechSpec §5: a
    # session_id link used to be a bearer credential anyone could read a
    # conversation with. Now a thread already owned by someone else 403s
    # instead of silently being readable.
    owner = _get_thread_owner(session_id)
    if owner is not None and owner != user_id:
        raise HTTPException(status_code=403, detail="This conversation doesn't belong to you.")

    if not _try_consume_daily_quota():
        return AskResponse(answer=DAILY_LIMIT_MESSAGE, session_id=session_id, source_type="internal")

    if _looks_like_injection_attempt(question):
        _touch_thread(session_id, user_id, question)
        return AskResponse(answer=REFUSAL_MESSAGE, session_id=session_id, source_type="internal")

    result = run_agent(
        question,
        session_id=session_id,
        match_count=request.match_count,
    )
    _touch_thread(session_id, user_id, question)

    return AskResponse(
        answer=result["answer"],
        session_id=session_id,
        source_type=result["source_type"],
        expert_note=result["expert_note"],
        sources=[Source(**s) for s in result["sources"]],
        chart_path=result["chart_path"],
        chart_image=result["chart_image"],
        web_findings=(
            [WebFinding(**f) for f in result["web_findings"]]
            if result["web_findings"] is not None
            else None
        ),
        internal_analysis=result["internal_analysis"],
        prediction_status=result["prediction_status"],
        prediction_content=result["prediction_content"],
        prediction_fallback=result["prediction_fallback"],
    )


class PendingPrediction(BaseModel):
    id: int
    topic: str
    draft_content: str
    created_at: str


class ReviewRequest(BaseModel):
    approve: bool
    reviewer_note: str | None = None


# Backs review.html (docs/TechSpec_v1.1.md §4.2) — no auth, deliberately not
# linked from index.html/ask.html. Fine for a single-operator demo; see the
# Non-Goals in docs/PRD_v1.1.md if this ever needs to be public-safe.
@app.get("/predictions", response_model=list[PendingPrediction])
def get_pending_predictions():
    return list_pending_predictions()


@app.post("/predictions/{prediction_id}/review")
def post_prediction_review(prediction_id: int, request: ReviewRequest):
    review_prediction(prediction_id, approve=request.approve, reviewer_note=request.reviewer_note)
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}
