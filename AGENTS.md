# OsiPress development notes

- Use Python 3.11. Run `python -m pytest -q` before proposing a change.
- Keep changes narrow. Do not add a dependency, background service, or new
  abstraction unless the current code needs it.
- Every database schema change needs an Alembic revision; do not use
  `Base.metadata.create_all()` for migrations.
- `articles.id` is also the Qdrant point id. Never renumber article ids.
- Qdrant is the normal hybrid-search path; Postgres is the outage fallback.
  Keep their dense/sparse inputs and reciprocal-rank-fusion behavior aligned.
- Ingestion writes Postgres first, then Qdrant. A failed Qdrant upsert can be
  repaired with the backfill script; Postgres remains the source of truth.
- Existing archive data predates `ingestion_runs`, so preserve the legacy
  archive fallback unless a migration explicitly replaces that history.
- Do not commit, push, or deploy unless explicitly asked. Use only the
  existing repository author identity and do not add co-authors.

See `docs/architecture.md` and `docs/search.md` before changing ingestion or
search.
