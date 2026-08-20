# Evaluation Report — v1.1

Questions: 21 across 5 topics.

## Metric scores by variant (0-10, higher is better)

| Variant | Answer Relevancy | Faithfulness | Context Precision | Context Recall (approx.) |
|---|---|---|---|---|
| baseline | 8.0 | — | — | — |
| full_product | 9.6 | 9.5 | 8.2 | 9.6 |
| pure_vector | 9.7 | 9.9 | 9.0 | 8.5 |
| pure_keyword | 3.8 | 10.0 | 0.0 | 0.0 |
| no_rerank | 9.2 | 10.0 | 8.7 | 8.8 |
| no_filter | 9.3 | 10.0 | 8.3 | 8.5 |

## Pairwise win rate: full_product vs. baseline

full_product won **57.1%** of 21 head-to-head comparisons.

## Ablation deltas vs. full_product (Faithfulness score)

| Variant removed | Faithfulness | Delta vs. full product |
|---|---|---|
| pure_vector | 9.9 | +0.3 |
| pure_keyword | 10.0 | +0.5 |
| no_rerank | 10.0 | +0.5 |
| no_filter | 10.0 | +0.5 |

## Notes

- Context Recall is a judge approximation, not a precise measurement — there is no labeled set of "chunks that should have been retrieved" to check against.
- LLM-as-judge has its own biases (e.g. toward longer answers) — spot-check a sample of scored items manually before treating these numbers as final.