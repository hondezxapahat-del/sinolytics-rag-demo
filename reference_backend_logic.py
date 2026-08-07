# reference_backend_logic.py
#
# 这不是一个能直接运行的完整文件——是给 Claude Code 参考的逻辑骨架。
# 把这个逻辑接进你现有的 api.py，函数名要换成你项目里实际的名字
# （比如 match_documents / search_documents / generate_chart 这些）。
#
# 核心设计原则（这是这次改动最重要的部分，务必保留）：
# 1. expert_note 绝不是"只要是内部检索就一定生成"——必须先检查检索结果
#    跟当前问题的相关性够不够高（用 rerank 分数做门槛），不够高就不生成，
#    前端也就不会显示这个框。宁可什么都不说，也不能编造关联性。
# 2. conversation_history 是否影响这次回答，交给 LLM 在 prompt 里自己判断，
#    不是"只要有历史就强行拼接"——新问题如果是全新话题，agent 应该把它当
#    独立问题处理，忽略掉不相关的历史。

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

load_dotenv()

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# ---------------------------------------------------------------------
# 相关性门槛：低于这个 rerank 分数，就认为检索结果跟问题关系不够大，
# 不生成 expert_note，也不能拿来东拉西扯。具体数值要按你实际的打分
# 范围调（比如如果你的rerank是0-10分，这里可能设成6-7比较合理）。
# ---------------------------------------------------------------------
RELEVANCE_THRESHOLD = 6.5


@tool
def search_internal_documents(query: str) -> dict:
    """
    在 Sinolytics 内部知识库里检索相关内容。
    返回值包含: answer（基于检索内容生成的回答）、
    expert_note（仅当检索内容相关性足够高时才有值，否则为空字符串）、
    is_relevant（相关性是否达标的布尔值，供上层判断要不要显示expert_note）
    """
    # TODO: 替换成你项目里真实的检索+rerank逻辑
    # candidates = hybrid_search(query)          # 向量+关键词混合检索
    # reranked = rerank(query, candidates)       # LLM打分排序
    # top_chunks = reranked[:3]
    # top_score = top_chunks[0]['relevance_score'] if top_chunks else 0
    #
    # answer = build_prompt_and_generate(query, top_chunks)
    #
    # if top_score >= RELEVANCE_THRESHOLD:
    #     expert_note = summarize_prior_experience(top_chunks, query)
    # else:
    #     expert_note = ""   # 相关性不够，不生成，不显示
    #
    # return {"answer": answer, "expert_note": expert_note, "is_relevant": top_score >= RELEVANCE_THRESHOLD}
    raise NotImplementedError("接入你项目里实际的检索函数")


@tool
def generate_price_chart(topic: str) -> dict:
    """
    根据结构化数据生成图表，返回 {"chart_image": "base64字符串", "answer": "简短说明文字"}
    """
    # TODO: 替换成你项目里真实的画图逻辑（plot_price_trend.py那套）
    raise NotImplementedError("接入你项目里实际的画图函数")


# 联网搜索工具，LangChain 已经封装好，不用自己写对接代码
web_search_tool = TavilySearch(max_results=3)

tools = [search_internal_documents, generate_price_chart, web_search_tool]

# ---------------------------------------------------------------------
# System prompt 是防止"生拉硬拽"的关键——明确告诉模型：
# 历史对话只在真正相关时才参考，新话题要独立处理。
# ---------------------------------------------------------------------
SYSTEM_PROMPT = """You are a China policy analysis assistant for Sinolytics.

Available tools:
- search_internal_documents: use for questions about China policy, industrial trends, supply chains, cybersecurity — anything likely covered by internal reports.
- generate_price_chart: use when the user explicitly asks to see a chart, trend, or visualization of data.
- web_search: use only when the question requires current/recent information that internal documents are unlikely to cover (e.g. "this week", "latest", specific recent events).

Important rules about conversation history:
- Only treat the new question as connected to prior turns if it is clearly a follow-up (e.g. uses "this", "that", "it" referring to the previous topic, or explicitly continues the same subject).
- If the new question introduces an unrelated topic, treat it as a fresh, independent question. Do NOT reference or connect it to earlier unrelated topics just because they appear in the conversation history.
- Never fabricate a connection between two topics (e.g. AI pricing and EV pricing) unless the retrieved content itself genuinely supports that connection.

Always answer in English, regardless of the language of retrieved source material.
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)


def handle_ask_request(question: str, conversation_history: list) -> dict:
    """
    这是 /ask 接口应该调用的主函数。
    conversation_history 格式: [{"role": "user"/"assistant", "content": "..."}]
    """
    # 把前端传来的历史转换成 LangChain 需要的消息格式
    chat_history = []
    for turn in conversation_history:
        if turn["role"] == "user":
            chat_history.append(HumanMessage(content=turn["content"]))
        else:
            chat_history.append(AIMessage(content=turn["content"]))

    result = agent_executor.invoke({
        "input": question,
        "chat_history": chat_history
    })

    # TODO: 根据 agent 实际调用了哪个工具，组装最终返回给前端的结构
    # 需要包含: answer, source_type ('internal' / 'web'), expert_note (可为空), chart_image (可为空)
    #
    # 一种做法：让 search_internal_documents / web_search_tool 各自在
    # 工具函数内部就把 source_type 信息带出来，агent_executor 的中间步骤
    # (result["intermediate_steps"]) 里能看到具体调用了哪个工具，
    # 可以从那里提取，而不是靠猜测。

    return {
        "answer": result["output"],
        # 下面这两行是占位，需要根据实际调用的工具来正确赋值
        "source_type": "internal",
        "expert_note": "",
    }
