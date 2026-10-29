# Bundled public handbook search data

`handbook.json.gz` contains a portable snapshot of 970 searchable sections from
GitLab's public handbook and their precomputed search vectors. It is restored
automatically when the application's local search collection is empty.

Each section includes its original title and source URL. Only URLs in
`data/gitlab_seed_urls.txt` are accepted by the exporter; local documents and
sources outside that list are excluded. The underlying handbook content belongs
to its original authors; follow the source links for the current content and terms.
The snapshot reflects the existing local index at export time, not a live feed.

To refresh it, first update the local public handbook index, then run:

```bash
python -m scripts.ingest --limit 40
python scripts/export_demo_snapshot.py
```

Commit the updated snapshot. The local `.chroma/` directory stays ignored.
