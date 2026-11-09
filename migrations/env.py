"""Alembic environment for OsiPress.

The settings in here are load-bearing and each one exists for a specific
reason documented inline. Read the comments before changing any of them.
"""

from logging.config import fileConfig

from alembic import context
from pgvector.sqlalchemy import Vector
from sqlalchemy import create_engine

from shared.database import DATABASE_URL, Base, engine
import shared.models  # noqa: F401  REQUIRED: registers tables on Base.metadata


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# shared.models must already be imported above for this to be non-empty.
target_metadata = Base.metadata


# Indexes that exist in the database but are deliberately not compared against
# the models. idx_articles_source_captured is (source_id, captured_at DESC);
# Alembic does not compare index sort order, and expressing the DESC as a
# sa.text() expression makes autogenerate propose a spurious drop/create pair
# on every run. The index is owned by revision 0001 and declared in
# shared/models.py for humans to see.
UNMANAGED_INDEXES = {"idx_articles_source_captured"}


def get_url() -> str:
    """Resolve the database URL.

    `alembic -x url=...` wins, so scratch databases never need the real .env.
    Otherwise use shared.database.DATABASE_URL.

    Never read os.environ["DATABASE_URL"] here and never trust alembic.ini's
    sqlalchemy.url: the deployed .env has no DATABASE_URL, so
    shared/database.py's localhost fallback is the URL the app actually uses.
    Duplicating that fallback logic would let alembic and the app disagree
    about which database they are talking to.
    """

    return context.get_x_argument(as_dictionary=True).get("url") or DATABASE_URL


def include_object(obj, name, type_, reflected, compare_to):
    """Keep UNMANAGED_INDEXES out of autogenerate comparisons."""

    if type_ == "index" and name in UNMANAGED_INDEXES:
        return False
    if type_ == "table" and name == "alembic_version":
        return False
    return True


def compare_type(
    context_,
    inspected_column,
    metadata_column,
    inspected_type,
    metadata_type,
):
    """Suppress the phantom pgvector type change.

    SQLAlchemy's postgres dialect resolves the `vector` type through pgvector's
    ischema_names entry but does not carry the (1536) modifier through
    reflection, so the inspected type is VECTOR(dim=None) while the model says
    Vector(1536). With a plain `compare_type=True` that difference is reported
    on every single autogenerate run as

        op.alter_column('articles', 'embedding', type_=Vector(...))

    which, if anyone ever commits it, rewrites the whole articles table.

    Returning None for everything else falls through to Alembic's default
    comparison, so genuine type drift is still caught.
    """

    if isinstance(inspected_type, Vector) or isinstance(metadata_type, Vector):
        return False
    return None


def render_item(type_, obj, autogen_context):
    """Render pgvector columns with their import in generated revisions."""

    if type_ == "type" and isinstance(obj, Vector):
        autogen_context.imports.add("import pgvector.sqlalchemy")
        return f"pgvector.sqlalchemy.Vector(dim={obj.dim})"
    return False


COMMON = dict(
    target_metadata=target_metadata,
    include_object=include_object,
    compare_type=compare_type,
    render_item=render_item,
    # Left off deliberately. articles.captured_at carries server_default=now()
    # and revision 0003 adds '{}'::text[] to articles.tags; Postgres echoes
    # both back in a normalised form that never string-matches the model, so
    # turning this on produces permanent unfixable noise.
    compare_server_default=False,
    # Each revision gets its own transaction, so a failure part-way through a
    # multi-revision upgrade rolls back only the revision that failed and
    # alembic_version still points at the last one that fully succeeded.
    transaction_per_migration=True,
)


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (`alembic upgrade X --sql`)."""

    context.configure(
        url=get_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **COMMON,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""

    url = get_url()

    # Reuse the app's own engine when the URL is the app's own URL, so there is
    # exactly one pool configuration in play; build a throwaway engine for an
    # -x url override.
    connectable = engine if url == DATABASE_URL else create_engine(url)

    try:
        with connectable.connect() as connection:
            context.configure(connection=connection, **COMMON)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        if connectable is not engine:
            connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
