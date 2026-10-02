"""
Try semantic search from the command line (no LLM needed).

    python -m src.retrieval.search "how do I store files in the cloud?"
    python -m src.retrieval.search "kubernetes" -k 6 --category DevOps
"""

import argparse
import textwrap

from src.retrieval.retriever import search


def main() -> None:
    parser = argparse.ArgumentParser(description="Semantic search over the knowledge base.")
    parser.add_argument("query")
    parser.add_argument("-k", type=int, help="number of chunks to return (default: TOP_K)")
    parser.add_argument("--category", help='restrict to one category, e.g. "AWS Cloud"')
    parser.add_argument("--min-score", type=float, help="minimum cosine similarity, 0-1 (default: MIN_SCORE)")
    args = parser.parse_args()

    results = search(args.query, k=args.k, category=args.category, min_score=args.min_score)
    if not results:
        print("No relevant chunks found (nothing scored above the minimum similarity).")
        return

    for rank, result in enumerate(results, 1):
        meta = result.document.metadata
        print(f"{rank}. [{result.score:.2f}] {meta['chunk_id']}  -  {meta['topic']} ({meta['category']})")
        body = result.document.page_content.split("\n", 1)[1]  # drop the repeated topic header
        print(textwrap.indent(textwrap.shorten(" ".join(body.split()), width=200, placeholder=" ..."), "     "))


if __name__ == "__main__":
    main()
