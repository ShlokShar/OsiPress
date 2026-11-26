from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from cron.util.url import normalize_article_url

revision = '0005_seen_items'
down_revision = '0004_event_foundation'
branch_labels = None
depends_on = None


def upgrade():
    seen = op.create_table(
        'seen_items',
        sa.Column('outlet_id', sa.Integer, sa.ForeignKey('sources.id'), primary_key=True),
        sa.Column('guid', sa.Text, primary_key=True),
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'outlet_run_log',
        sa.Column('run_id', sa.Integer, sa.ForeignKey('ingestion_runs.id'), primary_key=True),
        sa.Column('outlet_id', sa.Integer, sa.ForeignKey('sources.id'), primary_key=True),
        sa.Column('feed_size', sa.Integer, nullable=False),
        sa.Column('new_items', sa.Integer, nullable=False),
        sa.Column('political', sa.Integer, nullable=False),
        sa.Column('processed', sa.Integer, nullable=False),
        sa.Column('skipped_by_cap', sa.Integer, nullable=False),
        sa.Column('gap', sa.Boolean, nullable=False),
        sa.Column('cheap_pass_calls', sa.Integer, nullable=False),
        sa.Column('full_pass_calls', sa.Integer, nullable=False),
        sa.Column('input_tokens', sa.Integer),
        sa.Column('output_tokens', sa.Integer),
    )
    op.create_table(
        'pending_items',
        sa.Column('outlet_id', sa.Integer, sa.ForeignKey('sources.id'), primary_key=True),
        sa.Column('guid', sa.Text, primary_key=True),
        sa.Column('article_id', sa.Integer, sa.ForeignKey('articles.id')),
        sa.Column('run_id', sa.Integer, sa.ForeignKey('ingestion_runs.id'), nullable=False),
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('link', sa.Text, nullable=False),
        sa.Column('headline', sa.Text, nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True)),
        sa.Column('political', sa.Boolean, nullable=False, server_default=sa.false()),
    )
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        'SELECT source_id, link, captured_at FROM articles '
        'UNION ALL SELECT articles.source_id, article_urls.url, articles.captured_at '
        'FROM article_urls JOIN articles ON articles.id = article_urls.article_id '
        'ORDER BY 3'
    ).execution_options(stream_results=True))
    batch = []
    for source_id, link, captured_at in rows:
        try:
            guid = normalize_article_url(link)
        except ValueError:
            continue
        batch.append({'outlet_id': source_id, 'guid': guid, 'first_seen': captured_at})
        if len(batch) == 100:
            connection.execute(insert(seen).values(batch).on_conflict_do_nothing())
            batch.clear()
    if batch:
        connection.execute(insert(seen).values(batch).on_conflict_do_nothing())


def downgrade():
    op.drop_table('pending_items')
    op.drop_table('outlet_run_log')
    op.drop_table('seen_items')
