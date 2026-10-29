from __future__ import annotations

import argparse
import csv

from rag.vector_store import retrieve


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate retrieval with Recall@k.")
    parser.add_argument("--questions", default="data/eval/questions.csv")
    parser.add_argument("--k", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    total = 0
    hits = 0
    with open(args.questions, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            total += 1
            passages = retrieve(row["question"], top_k=args.k)
            expected = row["expected_source_hint"].lower()
            match = any(expected in passage["source"].lower() for passage in passages)
            hits += int(match)
            status = "hit" if match else "miss"
            top_source = passages[0]["source"] if passages else "none"
            print(f"{status:4} | {row['question']} | top: {top_source}")

    recall = hits / total if total else 0
    print(f"\nRecall@{args.k}: {recall:.2%} ({hits}/{total})")


if __name__ == "__main__":
    main()
