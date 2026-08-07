"""Core tool implementations: document search (RAG) and chart generation.

Kept independent of how the agent routes to them (see agent.py) — this module
doesn't know about LangChain at all, so the existing retrieval/chart behavior
is untouched by how the agent is wired.
"""

import base64
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from retrieval import hybrid_search, openai_client, rerank

load_dotenv()

CHAT_MODEL = "gpt-4o-mini"
PROJECT_DIR = Path(__file__).parent
CANDIDATE_COUNT = 5

# Below this rerank score (0-10 scale), retrieved content is considered too
# weakly related to the question to base an "expert note" on — expert_note
# is left empty rather than forcing a connection that isn't really there.
RELEVANCE_THRESHOLD = 6.5

# Below this rerank score, a chunk isn't included in the answer prompt at
# all. rerank() always returns exactly top_n candidates regardless of how
# relevant they actually are, so without this filter, weak/tangential
# chunks get padded into the context and the model dutifully turns them
# into extra "points" even though they're near-noise.
MIN_CONTEXT_SCORE = 5.0

CHART_TOPIC_KEYWORDS = [
    "nev", "ev", "electric vehicle", "price war", "car price", "vehicle price",
    "价格战", "新能源", "电动车", "车价",
    "byd", "xiaopeng", "tesla", "nio", "geely",
]

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
if TAVILY_API_KEY:
    from langchain_tavily import TavilySearch

    # topic="news" is what actually gets Tavily to return published_date per
    # result — with the default "general" topic it's usually absent. Without
    # a real date we annotate with source only, per the no-fabrication rule.
    _tavily = TavilySearch(max_results=5, topic="news")
else:
    _tavily = None

WEB_SEARCH_AVAILABLE = _tavily is not None


def build_prompt(question, matches):
    context = "\n\n---\n\n".join(match["content"] for match in matches)
    return (
        "请仅根据下面提供的资料回答问题。如果资料中没有相关信息，就说不知道。"
        "不要用你自己的通用知识去补充资料里没有的背景、历史或策略信息——"
        "哪怕这样会让回答显得更简短。\n\n"
        f"资料:\n{context}\n\n"
        f"问题: {question}\n\n"
        "无论检索到的资料是什么语言，都必须用英文回答。"
        "请充分利用资料里实际包含的信息展开回答，但不要为了显得详细就添加资料"
        "之外的内容——如果资料本身只够支撑一个简短的回答，那就给一个简短的回答。\n\n"
        "Format the answer like a professional consulting brief: open with "
        "exactly ONE sentence stating the core conclusion (no more than "
        "~25 words); if there are multiple genuinely distinct points, expand "
        "below with markdown bullets ('- ' at line start), each leading with "
        "a **bolded key term** then a brief explanation; if there's a clear "
        "implication or recommendation, give it its own short paragraph at "
        "the end. Avoid long unstructured paragraphs. Bullets require at "
        "least THREE genuinely separate ideas actually present in the "
        "passages above — not points added from your own knowledge. A "
        "single fact, a single number, or one thing compared to one other "
        "thing is NOT multiple points even if it could technically be split "
        "into two lines; state it as one or two plain sentences instead. "
        "Example: 'X costs $0.28 vs $25 for Y — about 89x cheaper' is one "
        "point, not two bullets. When in doubt, prefer prose over bullets, "
        "and prefer a short accurate answer over a longer embellished one."
    )


def summarize_prior_experience(matches, question):
    """One short sentence synthesizing what these specific passages support —
    never a bridge to some other topic or dataset not actually present here."""
    context = "\n\n---\n\n".join(match["content"] for match in matches)
    prompt = (
        "You are reminding a colleague what Sinolytics' own internal research "
        "already covers that's relevant to their current question. Write ONE "
        "short sentence (max ~30 words) summarizing the most relevant takeaway "
        "from the passages below.\n\n"
        "Only state what these specific passages actually support. Do not "
        "connect this topic to any other topic, dataset, or prior analysis "
        "that isn't directly present in the passages themselves — if the "
        "passages don't support a clean takeaway, write a more modest, "
        "narrowly-scoped sentence rather than reaching for a connection.\n\n"
        f"Question: {question}\n\n"
        f"Passages:\n{context}\n\n"
        "One-sentence note:"
    )
    completion = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content.strip()


def search_documents(query, match_count=3):
    candidates = hybrid_search(query, match_count=CANDIDATE_COUNT)
    if not candidates:
        return {
            "answer": "No relevant documents were found.",
            "sources": [],
            "expert_note": "",
            "is_relevant": False,
        }

    matches = rerank(query, candidates, top_n=match_count)
    top_score = matches[0]["relevance_score"] if matches else 0
    is_relevant = top_score >= RELEVANCE_THRESHOLD

    # Only pass chunks that actually clear the bar into the answer prompt —
    # don't pad in tangential filler just because rerank always returns
    # exactly top_n candidates. Fall back to the single best match so a
    # genuinely relevant top hit is never dropped entirely.
    context_matches = [m for m in matches if m["relevance_score"] >= MIN_CONTEXT_SCORE]
    if not context_matches and matches:
        context_matches = matches[:1]

    completion = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": build_prompt(query, context_matches)}],
    )
    answer = completion.choices[0].message.content

    # Gate expert_note strictly on relevance — never generate it just to
    # sound experienced when the retrieved content is a weak/tangential match.
    expert_note = summarize_prior_experience(matches, query) if is_relevant else ""

    return {
        "answer": answer,
        "sources": [
            {"content": m["content"], "relevance_score": m["relevance_score"]}
            for m in context_matches
        ],
        "expert_note": expert_note,
        "is_relevant": is_relevant,
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
        # Raw base64, no data-URI prefix — the frontend adds that itself.
        "chart_image": image_base64,
        "message": "Chart saved to price_trend.png",
    }


def _site_name(item):
    domain = urlparse(item.get("url", "")).netloc
    domain = re.sub(r"^www\.", "", domain)
    return domain or item.get("title") or "unknown source"


def _format_date(raw_date):
    """Only ever returns a real date Tavily gave us, or None — never a
    guess. Tavily's date strings look like 'Wed, 22 Apr 2026 15:38:51 GMT'."""
    if not raw_date:
        return None
    try:
        return parsedate_to_datetime(raw_date).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return raw_date


def _condense_web_findings(query, raw_items):
    """One point per source, in one batched LLM call — each point is
    grounded in exactly one excerpt (no mixing across sources, which would
    make per-finding source attribution unreliable)."""
    if not raw_items:
        return {}

    numbered = "\n\n".join(
        f"[{i}] {(item.get('content') or '')[:1500]}" for i, item in enumerate(raw_items)
    )
    prompt = (
        "For each numbered web page excerpt below, write ONE concise sentence "
        "(max ~30 words) stating the single most relevant takeaway for the "
        "question, using ONLY what that excerpt actually says. Do not mix "
        "information across excerpts, and do not add outside knowledge.\n\n"
        f"Question: {query}\n\n"
        f"Excerpts:\n{numbered}\n\n"
        "Respond with exactly one line per excerpt, in the format "
        "'[index]: sentence'. If an excerpt has nothing relevant to the "
        "question, respond with '[index]: SKIP'."
    )
    completion = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    text = completion.choices[0].message.content.strip()

    condensed = {}
    for line in text.splitlines():
        match = re.match(r"\[?(\d+)\]?\s*[:.\-]\s*(.+)", line.strip())
        if match:
            condensed[int(match.group(1))] = match.group(2).strip()
    return condensed


def search_web(query, match_count=3):
    """Web search (Tavily) plus an internal knowledge-base check run in
    parallel. web_findings is one entry per source, each tied to its own
    source name/URL/date — never a freeform paragraph, so attribution can't
    drift from the actual source. internal_analysis is only populated when
    the internal search clears the same relevance bar used elsewhere
    (RELEVANCE_THRESHOLD) — never included just because a search ran."""
    if _tavily is None:
        return {"web_findings": [], "internal_analysis": None}

    with ThreadPoolExecutor(max_workers=2) as executor:
        web_future = executor.submit(_tavily.invoke, {"query": query})
        internal_future = executor.submit(search_documents, query, match_count)
        raw = web_future.result()
        internal_result = internal_future.result()

    items = raw.get("results", []) if isinstance(raw, dict) else (raw or [])
    condensed = _condense_web_findings(query, items)

    web_findings = []
    for i, item in enumerate(items):
        point = condensed.get(i)
        if not point or point.strip().upper() == "SKIP":
            continue
        web_findings.append(
            {
                "content": point,
                "source": _site_name(item),
                "url": item.get("url", ""),
                "date": _format_date(item.get("published_date")),
            }
        )

    internal_analysis = (
        internal_result["answer"] if internal_result.get("is_relevant") else None
    )

    return {"web_findings": web_findings, "internal_analysis": internal_analysis}
