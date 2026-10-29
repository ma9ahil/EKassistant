# Retrieval evaluation

## Inputs and labels

- `questions.csv`: 25 manually authored questions, each with one reference handbook URL. The original 15 questions are retained and ten topic-specific questions were added before the comparison. This is a development set, not an independent held-out test set.
- `../demo/handbook.json.gz`: the exact bundled public corpus (970 sections, 23 source pages). Document vectors are reused, rather than re-embedded.
- Questions are embedded with `sentence-transformers/all-MiniLM-L6-v2`.
- Six reference pages are absent from the bundled snapshot. They are retained as misses in the overall score, with a separate coverage-conditioned score.
- Reference labels identify pages, not verified answer spans. Other pages may contain valid answers; exact-URL evaluation can penalize those alternatives.

## Controlled comparison

Both strategies use the same 25 nearest candidate sections from the same cosine-distance Chroma query, with `k=5`:

1. **Similarity:** take the first five sections, allowing multiple sections from one page.
2. **Source diversity:** preserve similarity order but keep only the highest-ranked section per unique source page, stopping after five pages or exhaustion of candidates.

The only changed variable is the final selection policy. The application and evaluator share `rag/ranking.py`. Similarity remains the application default because the measured gain is small and source diversity trades away depth within a page.

The evaluator creates a temporary database and does not touch the app's `.chroma/` directory, consume Cohere quota, apply the generation relevance threshold, or call an answer-generation model.

## Metrics

- **Hit@5:** fraction of all questions whose exact reference URL appears in the first five selected sections.
- **MRR@5:** mean of `1 / rank` for the first matching reference page; absent references contribute zero.
- **Hit@4:** the same hit metric truncated to four results, matching the maximum number of passages currently included in the generation prompt.
- **Covered questions:** the same metrics restricted to questions whose reference URL exists in the snapshot. This does not replace the full-set score.

Trailing slashes are normalized; parent and child URLs are not treated as equivalent. Multiple retrieved sections from one page do not earn extra relevance credit.

## Reproduce

From the repository root, after installing requirements:

```bash
python scripts/evaluate.py --k 5 --strategy compare --output data/eval/results.json
```

If the embedding model is already cached, `HF_HUB_OFFLINE=1` can be prefixed to the command. The first online run may download the model.

`results.json` includes the UTC run timestamp, SHA-256 hashes of both inputs, dependency versions, corpus and candidate counts, aggregate metrics, and every question's reference coverage, result URLs, and first relevant rank. Approximate-nearest-neighbor results or model outputs can vary with dependency/model versions.

## Observed results

| Strategy | Overall Hit@5 | Overall MRR@5 | Covered Hit@5 | Covered MRR@5 |
| --- | ---: | ---: | ---: | ---: |
| Similarity | 19/25 (76%) | 0.6200 | 19/19 (100%) | 0.8158 |
| Source diversity | 19/25 (76%) | 0.6233 | 19/19 (100%) | 0.8202 |

Hit@4 is also 76% overall for both strategies. Source diversity moves “What is covered by GitLab's security handbook?” from rank 4 to rank 3; the other reference ranks are unchanged.

Missing reference pages: asynchronous communication, handbook usage, product development flow, engineering quality, expenses, and customer success. Improving coverage is a more promising next step than claiming a broad win from this small ranking change.

These results do not measure answer correctness, citation faithfulness, latency, unanswerable-question detection, or conversation quality. Those require separate labels and evaluations.
