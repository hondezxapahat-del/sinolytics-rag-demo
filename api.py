"""FastAPI layer for the Sinolytics agent: exposes POST /ask, wiring each
request into the LangChain agent (agent.py) that routes between document
search, chart generation, and web search."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import run_agent

app = FastAPI(title="Docs Q&A Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class HistoryTurn(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class AskRequest(BaseModel):
    question: str
    match_count: int = 3
    conversation_history: list[HistoryTurn] = []


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
    source_type: str = "internal"  # "internal" or "web"
    expert_note: str = ""  # only non-empty when retrieval relevance cleared the threshold
    sources: list[Source] = []
    chart_path: str | None = None
    chart_image: str | None = None  # raw base64, no data-URI prefix
    web_findings: list[WebFinding] | None = None  # populated on the web_search path
    internal_analysis: str | None = None  # only when internal KB was also genuinely relevant


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question 不能为空")

    result = run_agent(
        question,
        history=[turn.model_dump() for turn in request.conversation_history],
        match_count=request.match_count,
    )

    return AskResponse(
        answer=result["answer"],
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
    )


@app.get("/health")
def health():
    return {"status": "ok"}
