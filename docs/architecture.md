# Architecture

OsiPress is a Flask site backed by Postgres, with a scheduled ingestion job.

```text
RSS feeds -> cron/script.py -> Postgres articles -> Qdrant points -> search
                                      |
                                      +-> ingestion runs/appearances -> feeds and archive
```

`cron/script.py` validates each feed, processes selected articles through the
AI services, and saves the canonical article in Postgres. The article is then
upserted to Qdrant using the same numeric id. A completed ingestion run makes
that edition visible atomically through `article_appearances`.

`article_urls` maps normalized URLs to canonical articles. The unique hash
prevents duplicate work when different feed URLs point at the same story.

The archive retains a legacy date-based query for articles collected before
ingestion runs existed. Do not remove it until that historical data has been
explicitly migrated.

Schema changes live in `migrations/`; run `alembic upgrade head` when
deploying. Production uses Python 3.11, systemd for the Flask app and the
ingestion timer, and Postgres as the source of truth.
