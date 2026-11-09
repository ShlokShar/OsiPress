"""baseline: the pre-Alembic production schema, recorded exactly as it exists

VERIFIED against production on 2026-11-08 via ./scripts/introspect_db.sh.
All six tables, every column type and nullability, the two indexes and all
six foreign keys below are copied from that dump.

This revision is NOT executed against production -- production is
`alembic stamp`ed to it, because it already has all of this. It exists so a
fresh database can be built from zero and so later revisions have a known
starting point.

Two things worth knowing about what is recorded here:

  * Columns are `character varying` (not `text`), because production was
    built by Base.metadata.create_all() from shared/models.py, where a bare
    Mapped[str] renders VARCHAR. In Postgres varchar-without-length and text
    are the same type with the same performance, so this is left alone
    rather than migrated.
  * There is NO index on articles(source_id, captured_at). Production has
    only articles_pkey. Revision 0002 adds that index -- it is a real
    improvement on 3,738 rows, not a drift fix.

Revision ID: 0001_baseline_prod_schema
Revises:
Create Date: 2026-11-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy

revision: str = "0001_baseline_prod_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Must precede articles: embedding is pgvector's vector type. Nothing in
    # the application has ever created this, which is why create_all on a
    # clean database has always failed.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "countries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="countries_pkey"),
    )

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("country_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("link", sa.String(), nullable=False),
        sa.Column("political_leaning", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["country_id"], ["countries.id"], name="sources_country_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id", name="sources_pkey"),
    )

    # Column order mirrors production's physical order (captured_at before
    # tags and embedding), which is NOT the declaration order in
    # shared/models.py. Keeping them aligned is what makes the pg_dump
    # verification diff come out empty.
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("headline", sa.String(), nullable=False),
        sa.Column("translated_headline", sa.String(), nullable=False),
        sa.Column("link", sa.String(), nullable=False),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column(
            "references_original",
            postgresql.ARRAY(sa.String()),
            nullable=False,
        ),
        sa.Column(
            "references_translated",
            postgresql.ARRAY(sa.String()),
            nullable=False,
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'::character varying[]"),
            nullable=False,
        ),
        sa.Column(
            "embedding", pgvector.sqlalchemy.Vector(dim=1536), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name="articles_source_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id", name="articles_pkey"),
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        # No server_default on production; status is set by the ORM.
        sa.Column("status", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="ingestion_runs_pkey"),
    )

    op.create_table(
        "article_urls",
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["article_id"], ["articles.id"], name="article_urls_article_id_fkey"
        ),
        sa.PrimaryKeyConstraint("url_hash", name="article_urls_pkey"),
    )
    op.create_index(
        "ix_article_urls_article_id",
        "article_urls",
        ["article_id"],
        unique=False,
    )

    op.create_table(
        "article_appearances",
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            name="article_appearances_article_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ingestion_runs.id"],
            name="article_appearances_run_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="article_appearances_source_id_fkey",
        ),
        sa.PrimaryKeyConstraint(
            "run_id", "source_id", "article_id", name="article_appearances_pkey"
        ),
    )
    op.create_index(
        "ix_article_appearances_run_source_position",
        "article_appearances",
        ["run_id", "source_id", "position"],
        unique=True,
    )


def downgrade() -> None:
    # Reverse foreign-key dependency order.
    op.drop_index(
        "ix_article_appearances_run_source_position",
        table_name="article_appearances",
    )
    op.drop_table("article_appearances")
    op.drop_index("ix_article_urls_article_id", table_name="article_urls")
    op.drop_table("article_urls")
    op.drop_table("ingestion_runs")
    op.drop_table("articles")
    op.drop_table("sources")
    op.drop_table("countries")

    # The `vector` extension is deliberately NOT dropped. Other databases in
    # the same cluster may use it, and dropping it would cascade-drop the
    # embedding column's type.
