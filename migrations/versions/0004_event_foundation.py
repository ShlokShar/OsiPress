"""add event clustering foundation

Revision ID: 0004_event_foundation
Revises: 0003_search_indexes
Create Date: 2026-11-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0004_event_foundation"
down_revision: Union[str, None] = "0003_search_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("published_at", sa.DateTime(timezone=True)))
    op.add_column("articles", sa.Column("neutral_fact", postgresql.JSONB()))
    op.create_table("topics", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(), nullable=False), sa.Column("description", sa.String(), nullable=False))
    op.create_table("events", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id")), sa.Column("title", sa.String()), sa.Column("status", sa.String(), nullable=False), sa.Column("outlet_count", sa.Integer(), nullable=False), sa.Column("article_count", sa.Integer(), nullable=False), sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False), sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False), sa.Column("first_published_at", sa.DateTime(timezone=True), nullable=False), sa.Column("titled_at", sa.DateTime(timezone=True)), sa.CheckConstraint("status IN ('hidden', 'visible')"))
    op.create_table("article_events", sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id"), primary_key=True), sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), nullable=False), sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False), sa.Column("match_path", sa.String(), nullable=False), sa.Column("match_score", sa.Float()), sa.CheckConstraint("match_path IN ('high', 'low', 'judge')"))
    op.create_table("match_log", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("run_id", sa.Integer(), sa.ForeignKey("ingestion_runs.id")), sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id"), nullable=False), sa.Column("candidates", postgresql.JSONB(), nullable=False), sa.Column("decision", sa.String(), nullable=False), sa.Column("path", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.CheckConstraint("path IN ('high', 'low', 'judge')"))


def downgrade() -> None:
    op.drop_table("match_log")
    op.drop_table("article_events")
    op.drop_table("events")
    op.drop_table("topics")
    op.drop_column("articles", "neutral_fact")
    op.drop_column("articles", "published_at")
