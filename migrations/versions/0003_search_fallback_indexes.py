"""add indexes for the Postgres search fallback

Qdrant is the normal search path, but shared/search_service.py falls back to
Postgres during an outage. These indexes keep that fallback usable as the
article table grows: a GIN index covers its English full-text expression and
an HNSW index covers cosine nearest-neighbor search over stored embeddings.

Both builds are intentionally transactional. The production table is small,
and an interrupted transactional migration leaves no half-built index.

Revision ID: 0003_search_indexes
Revises: 0002_articles_captured_idx
Create Date: 2026-11-16
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0003_search_indexes"
down_revision: Union[str, None] = "0002_articles_captured_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX idx_articles_search_fts ON articles USING gin "
        "(to_tsvector('english', translated_headline || ' ' || summary))"
    )
    op.execute(
        "CREATE INDEX idx_articles_embedding_hnsw ON articles USING hnsw "
        "(embedding vector_cosine_ops) WHERE embedding IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX idx_articles_embedding_hnsw")
    op.execute("DROP INDEX idx_articles_search_fts")
