"""Evaluation harness: baseline vs. full product vs. ablation variants, scored
by an LLM-as-judge on faithfulness / context precision / context recall /
answer relevancy, plus a pairwise win rate against baseline. Implements
docs/TechSpec_v1.1.md §4.3.

Run: python evaluate.py
Writes a markdown report to eval_report.md.

Context Recall is approximated (the judge has no labeled set of "chunks that
should have been retrieved" to check against) — treat it as a softer signal
than the other three metrics, not a precise measurement.
"""

import json
import re
from pathlib import Path

from eval_questions import EVAL_QUESTIONS
from retrieval import hybrid_search, keyword_search, openai_client, rerank, search
from tools import CANDIDATE_COUNT, CHAT_MODEL, MIN_CONTEXT_SCORE, build_prompt

REPORT_PATH = Path(__file__).parent / "eval_report.md"
TOP_N = 3


def _ask(prompt):
    completion = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content.strip()


def _filter_or_fallback(ranked):
    kept = [c for c in ranked if c["relevance_score"] >= MIN_CONTEXT_SCORE]
    return kept if kept else ranked[:1]


# --- Variants (each returns (answer, context_chunks)); context_chunks is
# None for baseline, since it has nothing to be faithful to. ---

def variant_baseline(question):
    return _ask(question), None


def variant_full_product(question):
    candidates = hybrid_search(question, match_count=CANDIDATE_COUNT)
    if not candidates:
        return _ask(build_prompt(question, [])), []
    ranked = rerank(question, candidates, top_n=TOP_N)
    context = _filter_or_fallback(ranked)
    return _ask(build_prompt(question, context)), context


def variant_pure_vector(question):
    candidates = search(question, match_count=CANDIDATE_COUNT)
    if not candidates:
        return _ask(build_prompt(question, [])), []
    ranked = rerank(question, candidates, top_n=TOP_N)
    context = _filter_or_fallback(ranked)
    return _ask(build_prompt(question, context)), context


def variant_pure_keyword(question):
    candidates = keyword_search(question, match_count=CANDIDATE_COUNT)
    if not candidates:
        return _ask(build_prompt(question, [])), []
    ranked = rerank(question, candidates, top_n=TOP_N)
    context = _filter_or_fallback(ranked)
    return _ask(build_prompt(question, context)), context


def variant_no_rerank(question):
    candidates = hybrid_search(question, match_count=CANDIDATE_COUNT)
    context = candidates[:TOP_N]
    return _ask(build_prompt(question, context)), context


def variant_no_filter(question):
    candidates = hybrid_search(question, match_count=CANDIDATE_COUNT)
    if not candidates:
        return _ask(build_prompt(question, [])), []
    ranked = rerank(question, candidates, top_n=TOP_N)
    return _ask(build_prompt(question, ranked)), ranked


VARIANTS = {
    "baseline": variant_baseline,
    "full_product": variant_full_product,
    "pure_vector": variant_pure_vector,
    "pure_keyword": variant_pure_keyword,
    "no_rerank": variant_no_rerank,
    "no_filter": variant_no_filter,
}

RAG_VARIANTS = [name for name in VARIANTS if name != "baseline"]


# --- Batched LLM-as-judge scoring (same "one prompt, one response" pattern
# as retrieval.score_relevance_batch) ---

def _parse_scores(text, n):
    scores = {}
    for line in text.splitlines():
        match = re.match(r"\[?(\d+)\]?\s*[:.\-]\s*(\d+(\.\d+)?)", line.strip())
        if match:
            scores[int(match.group(1))] = max(0.0, min(10.0, float(match.group(2))))
    return [scores.get(i, 0.0) for i in range(n)]


def score_answer_relevancy_batch(items):
    """items: [{question, answer}]. Does the answer actually address the question?"""
    if not items:
        return []
    numbered = "\n\n".join(
        f"[{i}] Question: {it['question']}\nAnswer: {it['answer']}" for i, it in enumerate(items)
    )
    prompt = (
        "For each numbered question/answer pair, rate 0-10 how directly and "
        "fully the answer addresses the question (10 = fully on-topic and "
        "responsive, 0 = ignores or evades the question).\n\n"
        f"{numbered}\n\n"
        "Respond with exactly one line per pair, format '[index]: score'."
    )
    return _parse_scores(_ask(prompt), len(items))


def score_faithfulness_batch(items):
    """items: [{question, answer, context}]. Is every claim in the answer
    actually supported by the context (vs. invented / hallucinated)?"""
    if not items:
        return []
    numbered = "\n\n".join(
        f"[{i}] Context: {' | '.join(c['content'] for c in it['context']) or '(empty)'}\n"
        f"Answer: {it['answer']}"
        for i, it in enumerate(items)
    )
    prompt = (
        "For each numbered item, rate 0-10 how faithful the answer is to the "
        "given context (10 = every claim is supported by the context, 0 = the "
        "answer contains claims the context does not support at all).\n\n"
        f"{numbered}\n\n"
        "Respond with exactly one line per item, format '[index]: score'."
    )
    return _parse_scores(_ask(prompt), len(items))


def score_context_precision_batch(items):
    """items: [{question, context}]. Of the retrieved chunks, how many are
    actually relevant to the question?"""
    if not items:
        return []
    numbered = "\n\n".join(
        f"[{i}] Question: {it['question']}\n"
        f"Retrieved chunks: {' | '.join(c['content'] for c in it['context']) or '(empty)'}"
        for i, it in enumerate(items)
    )
    prompt = (
        "For each numbered item, rate 0-10 how much of the retrieved content "
        "is actually relevant to answering the question (10 = every chunk is "
        "relevant, 0 = none of it is relevant).\n\n"
        f"{numbered}\n\n"
        "Respond with exactly one line per item, format '[index]: score'."
    )
    return _parse_scores(_ask(prompt), len(items))


def score_context_recall_batch(items):
    """items: [{question, context}]. Approximate — no labeled set of chunks
    that 'should' have been retrieved exists, so this is the judge's
    best-effort estimate of whether anything obviously relevant is missing,
    not a precise recall measurement."""
    if not items:
        return []
    numbered = "\n\n".join(
        f"[{i}] Question: {it['question']}\n"
        f"Retrieved chunks: {' | '.join(c['content'] for c in it['context']) or '(empty)'}"
        for i, it in enumerate(items)
    )
    prompt = (
        "For each numbered item, judge whether the retrieved chunks seem "
        "sufficient to fully answer the question, or whether something "
        "obviously relevant seems to be missing. Rate 0-10 (10 = nothing "
        "important seems missing, 0 = clearly insufficient to answer). You "
        "are not given the full source corpus, so judge based on whether the "
        "question itself seems answerable from what's shown.\n\n"
        f"{numbered}\n\n"
        "Respond with exactly one line per item, format '[index]: score'."
    )
    return _parse_scores(_ask(prompt), len(items))


def pairwise_win_rate(baseline_answers, product_answers, questions):
    """Anonymized A/B: which answer does the judge prefer, baseline or
    full_product? Returns (win_rate_pct, per_question_results)."""
    numbered = "\n\n".join(
        f"[{i}] Question: {q}\nA: {a}\nB: {b}"
        for i, (q, a, b) in enumerate(zip(questions, baseline_answers, product_answers))
    )
    prompt = (
        "For each numbered question, two answers (A and B) are given from "
        "different systems. Pick whichever answer is more accurate, complete, "
        "and useful for the question. Respond with exactly one line per item, "
        "format '[index]: A' or '[index]: B', followed by a short reason.\n\n"
        f"{numbered}"
    )
    text = _ask(prompt)
    picks = {}
    for line in text.splitlines():
        match = re.match(r"\[?(\d+)\]?\s*[:.\-]\s*([AB])", line.strip())
        if match:
            picks[int(match.group(1))] = match.group(2)

    results = []
    product_wins = 0
    for i, q in enumerate(questions):
        pick = picks.get(i, "A")  # default to baseline if unparsed, never overclaim
        won = pick == "B"
        product_wins += won
        results.append({"question": q, "product_won": won})
    win_rate = 100 * product_wins / len(questions) if questions else 0.0
    return win_rate, results


def run_variant(name, fn):
    results = []
    for item in EVAL_QUESTIONS:
        answer, context = fn(item["question"])
        results.append({**item, "answer": answer, "context": context or []})
        print(f"  [{name}] {item['topic']}/{item['type']}: done")
    return results


def build_report(all_results, metric_scores, win_rate, pairwise_results):
    lines = ["# Evaluation Report — v1.1\n"]
    lines.append(f"Questions: {len(EVAL_QUESTIONS)} across "
                  f"{len({q['topic'] for q in EVAL_QUESTIONS})} topics.\n")

    lines.append("## Metric scores by variant (0-10, higher is better)\n")
    lines.append("| Variant | Answer Relevancy | Faithfulness | Context Precision | Context Recall (approx.) |")
    lines.append("|---|---|---|---|---|")
    for variant in VARIANTS:
        m = metric_scores[variant]
        def avg(key):
            vals = m.get(key)
            return f"{sum(vals) / len(vals):.1f}" if vals else "—"
        lines.append(f"| {variant} | {avg('relevancy')} | {avg('faithfulness')} | {avg('precision')} | {avg('recall')} |")

    lines.append(f"\n## Pairwise win rate: full_product vs. baseline\n")
    lines.append(f"full_product won **{win_rate:.1f}%** of {len(pairwise_results)} head-to-head comparisons.\n")

    lines.append("## Ablation deltas vs. full_product (Faithfulness score)\n")
    full_faith = metric_scores["full_product"]["faithfulness"]
    full_avg = sum(full_faith) / len(full_faith) if full_faith else 0.0
    lines.append("| Variant removed | Faithfulness | Delta vs. full product |")
    lines.append("|---|---|---|")
    for variant in ["pure_vector", "pure_keyword", "no_rerank", "no_filter"]:
        vals = metric_scores[variant]["faithfulness"]
        avg = sum(vals) / len(vals) if vals else 0.0
        lines.append(f"| {variant} | {avg:.1f} | {avg - full_avg:+.1f} |")

    lines.append("\n## Notes\n")
    lines.append("- Context Recall is a judge approximation, not a precise measurement — "
                  "there is no labeled set of \"chunks that should have been retrieved\" to check against.")
    lines.append("- LLM-as-judge has its own biases (e.g. toward longer answers) — "
                  "spot-check a sample of scored items manually before treating these numbers as final.")

    return "\n".join(lines)


def main():
    print("Running all variants...")
    all_results = {name: run_variant(name, fn) for name, fn in VARIANTS.items()}

    print("Scoring...")
    metric_scores = {}
    for variant in VARIANTS:
        items = all_results[variant]
        relevancy = score_answer_relevancy_batch(
            [{"question": it["question"], "answer": it["answer"]} for it in items]
        )
        scores = {"relevancy": relevancy, "faithfulness": [], "precision": [], "recall": []}
        if variant in RAG_VARIANTS:
            scores["faithfulness"] = score_faithfulness_batch(items)
            scores["precision"] = score_context_precision_batch(items)
            scores["recall"] = score_context_recall_batch(items)
        metric_scores[variant] = scores

    print("Running pairwise comparison (full_product vs. baseline)...")
    baseline_answers = [it["answer"] for it in all_results["baseline"]]
    product_answers = [it["answer"] for it in all_results["full_product"]]
    questions = [it["question"] for it in EVAL_QUESTIONS]
    win_rate, pairwise_results = pairwise_win_rate(baseline_answers, product_answers, questions)

    report = build_report(all_results, metric_scores, win_rate, pairwise_results)
    REPORT_PATH.write_text(report, encoding="utf-8")

    raw_path = REPORT_PATH.with_suffix(".json")
    raw_path.write_text(
        json.dumps(
            {"results": all_results, "metric_scores": metric_scores,
             "win_rate": win_rate, "pairwise_results": pairwise_results},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\nReport written to {REPORT_PATH}")
    print(f"Raw data written to {raw_path}")


if __name__ == "__main__":
    main()
