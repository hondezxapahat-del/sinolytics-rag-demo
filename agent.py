"""LangChain tool-calling agent: routes each question to document search,
chart generation, or web search (or answers directly for greetings/small
talk), replacing the hand-rolled OpenAI tool_calls loop that used to live in
api.py.

`create_tool_calling_agent` + `AgentExecutor` (the API originally asked for)
were removed in LangChain 1.x. `create_agent` (LangGraph-based) is the
current replacement and does the same job — a tool-calling loop — just with
a different shape.
"""

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

import tools as core_tools

load_dotenv()

CHAT_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = (
    "You are a research assistant for Sinolytics, a China strategy advisory "
    "firm. You have three possible tools: search_documents, generate_chart, "
    "and a web search tool.\n\n"
    "Decide which one to use (if any) by matching the question against these "
    "rules IN ORDER — the first rule that matches wins, don't deliberate "
    "further once one matches:\n\n"
    "1. Greeting or small talk with no real question (e.g. 'hi', 'how are "
    "you') → answer directly, no tool call.\n"
    "2. Question explicitly asks to see a chart/graph/plot/visualization "
    "(trigger words: 'chart', 'graph', 'plot', 'visualize', '画图', '图表'), "
    "or is a comparison or share/proportion question about the EV price war "
    "(trigger words: 'compare', 'which is more', 'difference', 'share', "
    "'proportion', '对比', '哪个更', '区别', '占比', '份额') → call "
    "generate_chart with the topic.\n"
    "3. Question contains a timeliness/recency signal — trigger words: "
    "'newest', 'latest', 'recent', 'trend', 'this year', '最新', '最近', "
    "'趋势', '今年' (or similar) — → you MUST call the web search tool to get "
    "real current information. Do not answer from your own training "
    "knowledge for these, since it can be stale, and do not substitute "
    "search_documents for this — internal documents are not guaranteed to be "
    "current either. This rule applies EVEN IF the question is a follow-up "
    "continuing the current conversation topic: being a follow-up is never a "
    "reason to skip a fresh search when the question itself asks for timely "
    "information — re-search rather than answering from conversation "
    "history.\n"
    "4. Any other factual or analytical question about China AI pricing, "
    "export controls, or industry trends → call search_documents.\n\n"
    "Call at most one tool per turn unless the question genuinely requires "
    "combining two. Don't second-guess a rule that already matched.\n\n"
    "Internal documents and web search results differ in reliability: "
    "whenever part of your answer draws on the web search tool, explicitly "
    "label that part as coming from a web search, not the internal knowledge "
    "base.\n\n"
    "Conversation history: only treat the new question as connected to prior "
    "turns if it is clearly a follow-up (e.g. it uses 'this', 'that', 'it' "
    "referring to the previous topic, or explicitly continues the same "
    "subject). If the new question introduces an unrelated topic, treat it as "
    "a fresh, independent question — do not reference or connect it to "
    "earlier unrelated topics just because they appear in the conversation "
    "history. Never fabricate a connection between two topics (e.g. AI "
    "pricing and EV pricing) unless the retrieved content itself genuinely "
    "supports that connection. Note that this history guidance is about "
    "whether to connect topics, not about whether to search — rule 3 above "
    "always overrides it when a timeliness signal is present.\n\n"
    "Always respond in English. When you use information from a tool, use "
    "everything relevant that tool actually returned — don't cut a genuinely "
    "detailed source down to something terse. But never pad an answer with "
    "your own general/background knowledge (context, history, strategy, "
    "market color, etc.) that the tool result didn't actually contain, just "
    "to seem more thorough or to reach the bullet threshold below. If a tool "
    "only returned enough for a short answer, give a short answer — that's "
    "correct, not a shortcoming to compensate for.\n\n"
    "Format the answer like a professional consulting brief:\n"
    "- Open with exactly ONE sentence stating the core conclusion, no more "
    "than ~25 words.\n"
    "- If the topic has multiple genuinely distinct points, expand below it "
    "with markdown bullet points (each line starting with '- '), each one "
    "leading with a **bolded key term** followed by a brief explanation.\n"
    "- If there is a clear implication or recommendation, put it in its own "
    "short paragraph at the very end, separate from the bullets.\n"
    "- Avoid long unstructured paragraphs — keep it crisp, like an analyst "
    "brief.\n"
    "- Bullets require at least THREE genuinely separate ideas actually "
    "present in what the tools returned (distinct causes, distinct risks, "
    "distinct facts about different things) — not points you supplied from "
    "your own knowledge. A single fact, a single number, or one thing "
    "compared to one other thing is NOT multiple points, even if you could "
    "technically split it into two lines — state it as one or two plain "
    "sentences instead. Example: 'X costs $0.28 vs $25 for Y — about 89x "
    "cheaper' is one point, not two bullets. When in doubt, prefer prose "
    "over bullets, and prefer a short accurate answer over a longer "
    "embellished one."
)

_model = ChatOpenAI(model=CHAT_MODEL)


def _build_tools(capture, match_count):
    @tool
    def search_documents(query: str) -> str:
        """Search the internal knowledge base (Sinolytics reports on Chinese
        AI pricing and adoption, export controls, industry trends, etc.) and
        return an answer grounded in the retrieved passages. Use this for any
        factual or analytical question that might be covered by the stored
        documents."""
        result = core_tools.search_documents(query, match_count=match_count)
        capture["sources"] = result["sources"]
        capture["expert_note"] = result["expert_note"]
        capture["source_type"] = "internal"
        return result["answer"]

    @tool
    def generate_chart(topic: str) -> str:
        """Generate a chart. Only call this when the question involves a time
        trend, a comparison, a share/proportion/quantity, or an explicit
        request for a chart/graph/plot/visualization. Do not call this for
        plain conceptual or explanatory questions that don't need a visual.
        Currently only one chart is available: average price trend by brand
        (BYD, Xiaopeng, Tesla, NIO, Geely) during China's NEV/EV price war,
        2023-2024. Pass the topic the user asked about — if it isn't the EV
        price war, the tool will report that no matching chart is
        available."""
        result = core_tools.generate_chart(topic)
        capture["source_type"] = "internal"
        if "chart_image" in result:
            capture["chart_path"] = result["chart_path"]
            capture["chart_image"] = result["chart_image"]
            return result["message"]
        return result["error"]

    tool_list = [search_documents, generate_chart]

    if core_tools.WEB_SEARCH_AVAILABLE:
        @tool
        def web_search(query: str) -> str:
            """Search the public web for current or recent information that
            the internal knowledge base is unlikely to cover — breaking news,
            recent data, or events after the knowledge base's cutoff. Do not
            use this for questions the internal knowledge base can already
            answer. Also checks the internal knowledge base alongside the web
            search, in case there's relevant prior analysis to surface too."""
            result = core_tools.search_web(query, match_count=match_count)
            capture["source_type"] = "web"
            capture["web_findings"] = result["web_findings"]
            capture["internal_analysis"] = result["internal_analysis"]

            n = len(result["web_findings"])
            note = (
                f"Found {n} web result(s); they've already been formatted "
                "with sources as structured data for the user, so just give a "
                "brief one-sentence acknowledgment — do not restate their "
                "content in detail."
            )
            if result["internal_analysis"]:
                note += (
                    " Relevant internal prior analysis was also found and "
                    "will be shown to the user separately — briefly mention "
                    "it exists, don't repeat its content either."
                )
            return note

        tool_list.append(web_search)

    return tool_list


def run_agent(question, history=None, match_count=3):
    """Run one turn of the agent. `history` is a list of {"role", "content"}
    dicts (role is "user" or "assistant") from earlier turns in the
    conversation, oldest first."""
    capture = {"source_type": "internal"}
    agent = create_agent(
        model=_model,
        tools=_build_tools(capture, match_count),
        system_prompt=SYSTEM_PROMPT,
    )

    messages = [dict(turn) for turn in (history or [])]
    messages.append({"role": "user", "content": question})

    result = agent.invoke({"messages": messages})
    answer = result["messages"][-1].content

    return {
        "answer": answer,
        "source_type": capture.get("source_type", "internal"),
        "expert_note": capture.get("expert_note", ""),
        "sources": capture.get("sources", []),
        "chart_path": capture.get("chart_path"),
        "chart_image": capture.get("chart_image"),
        "web_findings": capture.get("web_findings"),
        "internal_analysis": capture.get("internal_analysis"),
    }
