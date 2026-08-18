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
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from retrieval import embed_query, hybrid_search, openai_client, rerank, supabase

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
    # time_range="month" trims clearly stale results at the source rather
    # than after the fact — "week" was considered but rejected as too narrow
    # for low-volume niche topics like China policy briefs, which can go
    # weeks between real developments without going stale.
    _tavily = TavilySearch(max_results=5, topic="news", time_range="month")
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
        "之外的内容——如果资料本身只够支撑一个简短的回答，那就给一个简短的回答。"
        "尤其注意：不要凭自己的印象编造或默认某个年份/日期——只有当资料原文里"
        "明确出现某个具体年份时，才能在回答里提到它；资料没写明年份的，就不要"
        "加上任何年份限定（比如'截至2024年'这类表述），哪怕这样会让回答听起来"
        "不够具体。\n\n"
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

    # search_web is only ever invoked for timeliness-signaled questions (per
    # agent.py's routing rule 3), so it's safe to always bias the Tavily
    # query toward recency here rather than re-detecting timeliness intent.
    # The internal search below intentionally uses the original query —
    # appending date hints would only hurt vector/keyword matching against
    # documents that aren't scored by recency.
    tavily_query = f"{query} (as of {datetime.now().year}, latest)"

    with ThreadPoolExecutor(max_workers=2) as executor:
        web_future = executor.submit(_tavily.invoke, {"query": tavily_query})
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


def _draft_trend_prediction(topic):
    """Generate a prediction draft in the internal-analyst voice, using
    retrieved internal passages purely as a style/tone reference (see
    docs/TechSpec_v1.1.md §4.2) — same "prompt + a few real passages"
    technique as summarize_prior_experience, not a new modeling approach."""
    candidates = hybrid_search(topic, match_count=CANDIDATE_COUNT)
    matches = rerank(topic, candidates, top_n=3) if candidates else []
    context = "\n\n---\n\n".join(m["content"] for m in matches)

    prompt = (
        "You are drafting a short, forward-looking trend prediction in the "
        "voice of a Sinolytics analyst, for internal review before it is "
        "ever shown to a client. Base the prediction's reasoning style on "
        "the passages below (if any) — match their tone and how they reason "
        "from evidence, but the prediction itself is necessarily your own "
        "forward-looking judgment, not something copied from the passages. "
        "Keep it to 2-4 sentences. Do not claim more certainty than a "
        "reasonable forecast warrants.\n\n"
        f"Topic: {topic}\n\n"
        f"Reference passages (style/context only):\n{context or '(none found)'}\n\n"
        "Draft prediction:"
    )
    completion = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content.strip()


def _fallback_internal_analysis(topic):
    """Regular (non-predictive) internal analysis, shown while a prediction
    is pending review. Explicitly returns None rather than an empty string
    when there's nothing to fall back on, so the caller can honestly say so
    instead of showing a blank block (the "double-empty" edge case in
    docs/TechSpec_v1.1.md §4.2)."""
    result = search_documents(topic)
    return result["answer"] if result["sources"] else None


def generate_trend_prediction(topic):
    """Check the approved/pending prediction library first via embedding
    similarity (match_trend_prediction RPC); only generate + queue a new
    draft if nothing close enough already exists. Predictions are never
    returned directly to a user from here — that only happens after a human
    approves them via review.html (docs/TechSpec_v1.1.md §4.2)."""
    topic_embedding = embed_query(topic)
    match = (
        supabase.rpc("match_trend_prediction", {"query_embedding": topic_embedding})
        .execute()
        .data
    )

    if match:
        # match_trend_prediction only ever returns pending/approved rows —
        # a rejected draft never blocks a fresh one from being generated.
        record = match[0]
        if record["status"] == "approved":
            return {"status": "approved", "content": record["draft_content"]}
        return {"status": "pending", "fallback": _fallback_internal_analysis(topic)}

    draft = _draft_trend_prediction(topic)
    supabase.table("trend_predictions").insert(
        {
            "topic": topic,
            "topic_embedding": topic_embedding,
            "draft_content": draft,
            "status": "pending",
        }
    ).execute()
    return {"status": "pending", "fallback": _fallback_internal_analysis(topic)}


def list_pending_predictions():
    """Backs review.html — the human-confirmation queue (docs/TechSpec_v1.1.md §4.2)."""
    result = (
        supabase.table("trend_predictions")
        .select("id, topic, draft_content, created_at")
        .eq("status", "pending")
        .order("created_at")
        .execute()
    )
    return result.data


def review_prediction(prediction_id, approve, reviewer_note=None):
    """Approve/reject a pending prediction from review.html. Rejected drafts
    stay in the table (status="rejected") rather than being deleted, purely
    as a record — match_trend_prediction's SQL excludes rejected rows, so a
    future similar topic always regenerates a fresh draft instead of
    matching against a stale rejected one."""
    supabase.table("trend_predictions").update(
        {
            "status": "approved" if approve else "rejected",
            "reviewed_at": datetime.now().isoformat(),
            "reviewer_note": reviewer_note,
        }
    ).eq("id", prediction_id).execute()
