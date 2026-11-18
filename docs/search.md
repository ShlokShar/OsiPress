# Search

Search is hybrid: dense OpenAI embeddings supply semantic relevance and BM25
supplies keyword relevance. Qdrant stores both vectors and fuses their top 50
results with reciprocal rank fusion (RRF); Postgres has equivalent fallback
queries for a Qdrant outage.

The two paths deliberately use the same RRF rule: `1 / (60 + rank)` using
one-based ranks. Qdrant reports zero-based ranks, so its configured constant
is 61. Keep this relationship intact if either implementation changes.

Qdrant point ids mirror `articles.id`; the hydrated article content always
comes from Postgres. The `idx_articles_search_fts` and
`idx_articles_embedding_hnsw` indexes exist only to keep the fallback fast.

Check consistency without writing anything:

```sh
QDRANT_URL=... QDRANT_API_KEY=... python scripts/audit_qdrant.py \
  --database-url postgresql:///osipress --since 2026-09-01
```

The optional `--since` limits missing-point checks to recent articles, but
orphan detection always compares every Qdrant point with every Postgres id.
