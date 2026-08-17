"""Hand-designed evaluation set for the four topics actually present in the
retrieval corpus (see docs/TechSpec_v1.1.md §4.3). Each question is tagged
with its topic and type so results can be broken down either way.

Topics reflect what embed_and_store.py actually ingests (docs/*.txt) —
china_nev_price_war.csv is chart-only data and is not retrievable, so it is
not a topic here even though generate_chart supports it.
"""

EVAL_QUESTIONS = [
    # --- Topic: Chinese AI model pricing/market (1.txt) ---
    {
        "topic": "ai_pricing",
        "type": "single_fact",
        "question": "DeepSeek V4 Flash 每百万输出 token 收费是多少美元？",
    },
    {
        "topic": "ai_pricing",
        "type": "single_fact",
        "question": "Claude Opus 4.8 每百万输出 token 收费是多少美元，比 DeepSeek V4 Flash 贵多少倍？",
    },
    {
        "topic": "ai_pricing",
        "type": "multi_point",
        "question": "中国 AI 大模型能把价格做得这么低，资料里提到了哪几个原因？",
    },
    {
        "topic": "ai_pricing",
        "type": "multi_point",
        "question": "美国和中国的监管机构，各自对中国 AI 模型崛起做出了什么反应？",
    },
    {
        "topic": "ai_pricing",
        "type": "cross_topic_confusion",
        "question": "中国 AI 大模型的价格战，跟中国工业机器人市场的竞争格局有什么关系？",
    },

    # --- Topic: China desktop AI office-agent market (2.txt) ---
    {
        "topic": "desktop_agent",
        "type": "single_fact",
        "question": "2026 年 6 月，WorkBuddy 的 PC 客户端访问量是多少？",
    },
    {
        "topic": "desktop_agent",
        "type": "single_fact",
        "question": "腾讯、阿里、字节三家公司加起来占了桌面 AI 办公 agent 市场多少比例的流量？",
    },
    {
        "topic": "desktop_agent",
        "type": "multi_point",
        "question": "中国桌面 AI 办公 agent 市场的竞争重心，正在从什么转向什么？",
    },
    {
        "topic": "desktop_agent",
        "type": "multi_point",
        "question": "阿里和字节各自在整合旗下哪些产品？",
    },

    # --- Topic: China industrial robot installations (3.txt) ---
    {
        "topic": "industrial_robots",
        "type": "single_fact",
        "question": "2024 年中国新增工业机器人安装量，占全球总量的比例是多少？",
    },
    {
        "topic": "industrial_robots",
        "type": "single_fact",
        "question": "IFR 数据显示，2024 年中国新增工业机器人安装量具体是多少台？",
    },
    {
        "topic": "industrial_robots",
        "type": "multi_point",
        "question": "十五五规划对工业自动化提出了什么样的战略定位？",
    },
    {
        "topic": "industrial_robots",
        "type": "multi_point",
        "question": "2021 年到 2024 年，中国工业机器人新增安装量的变化趋势是怎样的？",
    },

    # --- Topic: Export controls (whitepaper_export-controls.txt) ---
    {
        "topic": "export_controls",
        "type": "single_fact",
        "question": "中国现行出口管制体系的法律基础——《出口管制法》是哪一年颁布的？",
    },
    {
        "topic": "export_controls",
        "type": "single_fact",
        "question": "2010 年中国大幅削减稀土出口配额后，对全球市场产生了什么影响？",
    },
    {
        "topic": "export_controls",
        "type": "multi_point",
        "question": "资料中提到的瑞典石墨出口案例，说明了中国出口管制可能被用作什么样的工具？",
    },
    {
        "topic": "export_controls",
        "type": "multi_point",
        "question": "美国无人机制造商 Skydio 的案例，反映了中国出口管制/制裁工具有什么特点？",
    },
    {
        "topic": "export_controls",
        "type": "multi_point",
        "question": "资料认为，中国近年出口管制的驱动逻辑，跟过去相比发生了什么变化？",
    },

    # --- Uncovered-topic questions (should honestly say "don't know") ---
    {
        "topic": "uncovered",
        "type": "uncovered",
        "question": "根据资料，OpenAI 最新一轮融资的估值是多少？",
    },
    {
        "topic": "uncovered",
        "type": "uncovered",
        "question": "资料里如何评价中国动力电池技术相对于韩国企业的优势？",
    },
    {
        "topic": "uncovered",
        "type": "uncovered",
        "question": "根据资料，中国 2026 年新能源车全年销量预计是多少？",
    },
]
