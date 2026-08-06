"""RAG agent API: an LLM with function-calling decides whether to search documents,
generate a chart, or just answer directly (e.g. for greetings)."""

import base64
import json
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from retrieval import hybrid_search, openai_client, rerank

CHAT_MODEL = "gpt-4o-mini"
PROJECT_DIR = Path(__file__).parent
CANDIDATE_COUNT = 5

CHART_TOPIC_KEYWORDS = [
    "nev", "ev", "electric vehicle", "price war", "car price", "vehicle price",
    "价格战", "新能源", "电动车", "车价",
    "byd", "xiaopeng", "tesla", "nio", "geely",
]

SYSTEM_PROMPT = (
    "You are a research assistant for Sinolytics, a China strategy advisory firm. "
    "You have two tools available: search_documents, for looking up facts and analysis "
    "in the internal knowledge base, and generate_chart, for producing a chart. "
    "Call a tool only when it's actually needed to answer the question. For simple "
    "greetings or small talk that don't require any lookup, answer directly without "
    "calling a tool. Only call generate_chart when the question is about a time trend, "
    "a comparison, a share/proportion, or explicitly asks for a visualization — plain "
    "conceptual or explanatory questions should be answered with text (via "
    "search_documents if they need grounding), not a chart. Always respond in English, "
    "and when you use information from a tool, be thorough and detailed rather than "
    "terse."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": (
                "Search the internal knowledge base (Sinolytics reports on Chinese AI "
                "pricing and adoption, export controls, industry trends, etc.) and "
                "return an answer grounded in the retrieved passages. Use this for any "
                "factual or analytical question that might be covered by the stored "
                "documents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The question or search query to look up in the knowledge base.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_chart",
            "description": (
                "Generate a chart. Only call this when the question involves a time "
                "trend (e.g. 'change', 'trend', 'over the past few years', '变化', "
                "'趋势', '过去几年'), a comparison (e.g. 'compare', 'which is more', "
                "'difference', '对比', '哪个更', '区别'), a share/proportion/quantity "
                "(e.g. 'share', 'proportion', '份额', '占比'), or an explicit request "
                "for a chart/graph/plot/visualization. Do not call this for plain "
                "conceptual or explanatory questions that don't need a visual. "
                "Currently only one chart is available: average price trend by brand "
                "(BYD, Xiaopeng, Tesla, NIO, Geely) during China's NEV/EV price war, "
                "2023-2024. Pass the topic the user asked about — if it isn't the EV "
                "price war, the tool will report that no matching chart is available."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The chart topic the user asked about, in their own words.",
                    }
                },
                "required": ["topic"],
            },
        },
    },
]

app = FastAPI(title="Docs Q&A Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str
    match_count: int = 3


class Source(BaseModel):
    content: str
    relevance_score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[Source] = []
    chart_path: str | None = None
    chart_image: str | None = None


def build_prompt(question, matches):
    context = "\n\n---\n\n".join(match["content"] for match in matches)
    return (
        "请仅根据下面提供的资料回答问题。如果资料中没有相关信息，就说不知道。\n\n"
        f"资料:\n{context}\n\n"
        f"问题: {question}\n\n"
        "无论检索到的资料是什么语言，都必须用英文回答。"
        "请尽量详细、充分利用提供的资料信息展开回答，不要过于简略。"
    )


def search_documents(query, match_count=3):
    candidates = hybrid_search(query, match_count=CANDIDATE_COUNT)
    if not candidates:
        return {"answer": "No relevant documents were found.", "sources": []}

    matches = rerank(query, candidates, top_n=match_count)

    completion = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": build_prompt(query, matches)}],
    )
    answer = completion.choices[0].message.content
    return {
        "answer": answer,
        "sources": [
            {"content": m["content"], "relevance_score": m["relevance_score"]}
            for m in matches
        ],
    }


def generate_chart(topic):
    topic_lower = topic.lower()
    if not any(keyword in topic_lower for keyword in CHART_TOPIC_KEYWORDS):
        return {
            "error": (
                f"No chart is available for topic '{topic}'. Only the China NEV "
                "price war chart (BYD, Xiaopeng, Tesla, NIO, Geely) is currently "
                "supported."
            )
        }

    result = subprocess.run(
        [sys.executable, "plot_price_trend.py"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {"error": f"Chart generation failed: {result.stderr.strip()}"}

    image_bytes = (PROJECT_DIR / "price_trend.png").read_bytes()
    image_base64 = base64.b64encode(image_bytes).decode("ascii")

    return {
        "chart_path": "price_trend.png",
        "chart_image": f"data:image/png;base64,{image_base64}",
        "message": "Chart saved to price_trend.png",
    }


def run_tool_call(tool_call, match_count):
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments or "{}")

    if name == "search_documents":
        result = search_documents(args.get("query", ""), match_count=match_count)
        return result["answer"], result["sources"], None, None

    if name == "generate_chart":
        result = generate_chart(args.get("topic", ""))
        chart_path = result.get("chart_path")
        chart_image = result.get("chart_image")
        # Keep the base64 payload out of the model's context — it only needs
        # to know the chart was made, not see the image bytes.
        model_facing_result = {k: v for k, v in result.items() if k != "chart_image"}
        return json.dumps(model_facing_result), [], chart_path, chart_image

    error = {"error": f"Unknown tool: {name}"}
    return json.dumps(error), [], None, None


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question 不能为空")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    response = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        tools=TOOLS,
    )
    message = response.choices[0].message

    if not message.tool_calls:
        return AskResponse(answer=message.content, sources=[], chart_path=None)

    messages.append(message)

    sources = []
    chart_path = None
    chart_image = None
    for tool_call in message.tool_calls:
        tool_content, tool_sources, tool_chart_path, tool_chart_image = run_tool_call(
            tool_call, match_count=request.match_count
        )
        sources = sources or tool_sources
        chart_path = chart_path or tool_chart_path
        chart_image = chart_image or tool_chart_image
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_content,
            }
        )

    final = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
    )
    answer = final.choices[0].message.content

    return AskResponse(
        answer=answer,
        sources=[Source(**s) for s in sources],
        chart_path=chart_path,
        chart_image=chart_image,
    )


@app.get("/health")
def health():
    return {"status": "ok"}
