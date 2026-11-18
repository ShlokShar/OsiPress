"""Compare Postgres article ids with the Qdrant articles collection.

This is read-only. It reports missing Qdrant points for an optional recent
window, plus genuinely orphaned points by comparing against all Postgres ids.
"""

import argparse
import os
from datetime import datetime

from qdrant_client import QdrantClient
from sqlalchemy import create_engine, text


COLLECTION = "articles"
PAGE_SIZE = 1_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        required=True,
        help="SQLAlchemy Postgres URL, e.g. postgresql:///osipress",
    )
    parser.add_argument(
        "--since",
        type=datetime.fromisoformat,
        help="Only require Qdrant points for articles captured at or after ISO time",
    )
    return parser.parse_args()


def article_ids(engine, since: datetime | None = None) -> set[int]:
    statement = "SELECT id FROM articles"
    parameters = {}
    if since is not None:
        statement += " WHERE captured_at >= :since"
        parameters["since"] = since

    with engine.connect() as connection:
        return {row.id for row in connection.execute(text(statement), parameters)}


def qdrant_ids(client: QdrantClient) -> set[int]:
    ids: set[int] = set()
    offset = None
    while True:
        points, offset = client.scroll(
            COLLECTION,
            limit=PAGE_SIZE,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        ids.update(int(point.id) for point in points)
        if offset is None:
            return ids


def preview(ids: set[int]) -> str:
    values = sorted(ids)
    shown = ", ".join(str(value) for value in values[:20])
    return shown + (", ..." if len(values) > 20 else "")


def main() -> int:
    args = parse_args()
    engine = create_engine(args.database_url)
    client = QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ["QDRANT_API_KEY"],
    )

    try:
        all_postgres_ids = article_ids(engine)
        expected_ids = article_ids(engine, args.since)
        indexed_ids = qdrant_ids(client)
    finally:
        engine.dispose()

    missing = expected_ids - indexed_ids
    orphaned = indexed_ids - all_postgres_ids
    scope = f" since {args.since.isoformat()}" if args.since else ""
    print(f"Postgres articles{scope}: {len(expected_ids)}")
    print(f"Qdrant points: {len(indexed_ids)}")
    print(f"Missing Qdrant points: {len(missing)}")
    print(f"Orphaned Qdrant points: {len(orphaned)}")
    if missing:
        print(f"Missing ids: {preview(missing)}")
    if orphaned:
        print(f"Orphaned ids: {preview(orphaned)}")
    return 1 if missing or orphaned else 0


if __name__ == "__main__":
    raise SystemExit(main())
