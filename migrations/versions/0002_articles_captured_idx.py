"""add the articles(source_id, captured_at DESC) index

Production has only articles_pkey on articles, while the read path scans
source_id and captured_at constantly: get_headlines_by_country()'s legacy
branch groups by source_id taking max(captured_at) per source, and /archive
filters captured_at over a day range (shared/models.py). Both are sequential
scans today.

Deliberately NOT created CONCURRENTLY. At 3,738 rows the index builds in
milliseconds, so the brief ACCESS EXCLUSIVE lock does not matter, and
CONCURRENTLY would require an autocommit block -- which ends the
per-migration transaction that carries the alembic_version update, leaving
the index built but the revision unrecorded. Keep this revision
transactional. If articles ever grows to the point where the lock matters,
split the concurrent build into its own non-transactional revision rather
than adding an autocommit block here.

Note on the identifier: alembic_version.version_num is varchar(32) by
default, so revision ids must stay under 32 characters. A longer one fails
the version UPDATE with StringDataRightTruncation *after* the migration's
DDL has run.

Revision ID: 0002_articles_captured_idx
Revises: 0001_baseline_prod_schema
Create Date: 2026-11-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_articles_captured_idx"
down_revision: Union[str, None] = "0001_baseline_prod_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "idx_articles_source_captured"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "articles",
        ["source_id", sa.text("captured_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="articles")
