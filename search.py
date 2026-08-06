"""CLI: hybrid search — merge vector (match_documents) and keyword (keyword_search)
results into one deduped candidate set."""

import sys

from retrieval import hybrid_search


def main():
    question = " ".join(sys.argv[1:]).strip() or input("问题: ").strip()
    if not question:
        print("未输入问题")
        return

    matches = hybrid_search(question)
    if not matches:
        print("没有找到相关内容")
        return

    for i, match in enumerate(matches, 1):
        similarity = f"{match['similarity']:.4f}" if match["similarity"] is not None else "—"
        rank = f"{match['rank']:.4f}" if match["rank"] is not None else "—"
        print(f"\n[{i}] similarity={similarity} keyword_rank={rank}")
        print(match["content"])


if __name__ == "__main__":
    main()
