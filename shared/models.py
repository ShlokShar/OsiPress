
from collections import defaultdict
import hashlib
from datetime import (
    date,
    datetime,
    timedelta,
    timezone
)
from typing import (
    Any,
    Optional
)

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    func,
    inspect,
    String,
    Text,
    text,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column
)

from shared.database import (
    Base,
    SessionLocal,
    engine,
)


class Countries(Base):
    __tablename__ = 'countries'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()

    @classmethod
    def get_country(
        cls,
        name: str = "",
        country_id: int = -1
    ) -> Optional["Countries"]:
        """
        Receives a country object from either the name or its database id.

        :param name: the country name
        :param country_id: the country id as per Postgres
        :return: the country object
        """

        with SessionLocal() as session:
            if country_id > 0:
                return session.query(cls).filter(cls.id == country_id).first()
            return session.query(cls).filter(cls.name == name).first()


class Sources(Base):
    __tablename__ = 'sources'

    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey('countries.id'))
    name: Mapped[str] = mapped_column()
    link: Mapped[str] = mapped_column()
    political_leaning: Mapped[str] = mapped_column()

    @classmethod
    def get_source(cls, country_id: int, source_id: int) -> Mapped[int]:
        """
        Receives a source object from either the name or its database id.

        :param country_id: the country id as per Postgres
        :param source_id: the source id as per Postgres
        :return: the source object
        """

        with SessionLocal() as session:
            if source_id:
                return session.query(cls).filter(cls.id == source_id).first()
            return session.query(cls).filter(
                cls.country_id == country_id
            ).first()

    @classmethod
    def get_source_by_name(cls, country_id: int, name: str):
        """
        Receives a source object from either the name or its database id.

        :param country_id: the country id as per Postgres
        :param name: the source's name
        :return: the source object
        """

        with SessionLocal() as session:
            return session.query(cls).filter(
                cls.country_id == country_id, cls.name == name
            ).first()


class Articles(Base):
    __tablename__ = 'articles'

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey('sources.id'))
    headline: Mapped[str] = mapped_column()
    translated_headline: Mapped[str] = mapped_column()
    # Not unique, and it must not become unique: the same article can appear
    # under several feed URLs, and find_article_by_url picks a canonical row.
    link: Mapped[str] = mapped_column()
    summary: Mapped[str] = mapped_column()
    references_original: Mapped[list[str]] = mapped_column(ARRAY(String))
    references_translated: Mapped[list[str]] = mapped_column(ARRAY(String))
    # server_default matches production, which already carries it.
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        server_default=text("'{}'::character varying[]"),
    )
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(1536),
        nullable=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        # Declared so this index is visible in code and nobody drops it by
        # accident. It predates Alembic and is owned by revision 0001.
        # migrations/env.py keeps it out of autogenerate comparisons, because
        # Alembic cannot compare an index's sort order and would otherwise
        # propose a drop/create pair on every run.
        Index(
            'idx_articles_source_captured',
            'source_id',
            text('captured_at DESC'),
        ),
    )

    @staticmethod
    def add_article(article):
        """
        adds an article to the Postgres database.

        The commit expires every attribute, so the article is refreshed while
        the session is still open. Callers need this to read the id Postgres
        assigned on insert, which is what keys the article's point in Qdrant.

        :param article: the article object (includes the foreign source key)
        :return: the article object
        """

        with SessionLocal() as session:
            session.add(article)
            session.commit()
            session.refresh(article)

        return article

    def embedding_text(self) -> str:
        """
        Retrieves the translated headline and article summary to be embedded.
        :return: the text to be embedded
        """

        return f"{self.translated_headline}:{self.summary}"

    def to_dict(self):
        """
        Returns a dictionary version of the data.

        :return: a dictionary version of the data
        """

        return {
            "id": self.id,
            "source_id": self.source_id,
            "headline": self.headline,
            "translated_headline": self.translated_headline,
            "link": self.link,
            "summary": self.summary,
            "references_original": self.references_original,
            "references_translated": self.references_translated,
            "tags": self.tags,
        }


class ArticleURLs(Base):
    """Maps a normalized URL to the one canonical processed article."""

    __tablename__ = 'article_urls'

    url_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    article_id: Mapped[int] = mapped_column(
        ForeignKey('articles.id'),
        nullable=False,
        index=True,
    )


class IngestionRuns(Base):
    """A collection attempt that becomes visible only after it succeeds."""

    __tablename__ = 'ingestion_runs'

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String, default='pending')


class ArticleAppearances(Base):
    """Places a canonical article in a source's slot for one edition run."""

    __tablename__ = 'article_appearances'

    run_id: Mapped[int] = mapped_column(
        ForeignKey('ingestion_runs.id'),
        primary_key=True,
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey('sources.id'),
        primary_key=True,
    )
    article_id: Mapped[int] = mapped_column(
        ForeignKey('articles.id'),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index(
            'ix_article_appearances_run_source_position',
            'run_id',
            'source_id',
            'position',
            unique=True,
        ),
    )


def find_article_by_url(
    normalized_url: str,
    original_url: str,
) -> Optional[Articles]:
    """Find a processed URL, adopting an exact legacy row when necessary."""

    url_hash = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()
    with SessionLocal() as session:
        article = (
            session.query(Articles)
            .join(ArticleURLs, ArticleURLs.article_id == Articles.id)
            .filter(
                ArticleURLs.url_hash == url_hash,
                ArticleURLs.url == normalized_url,
            )
            .first()
        )
        if article:
            return article

        article = (
            session.query(Articles)
            .filter(Articles.link == original_url)
            .order_by(Articles.id)
            .first()
        )
        if not article:
            return None

        session.add(ArticleURLs(
            url_hash=url_hash,
            url=normalized_url,
            article_id=article.id,
        ))
        session.commit()
        session.refresh(article)
        return article


def add_canonical_article(article: Articles, normalized_url: str) -> Articles:
    """Save a processed article and claim its normalized URL atomically."""

    with SessionLocal() as session:
        session.add(article)
        session.flush()
        session.add(ArticleURLs(
            url_hash=hashlib.sha256(
                normalized_url.encode("utf-8")
            ).hexdigest(),
            url=normalized_url,
            article_id=article.id,
        ))
        session.commit()
        session.refresh(article)
        return article


def start_ingestion_run(started_at: datetime) -> int:
    """Create a pending ingestion run and return its id."""

    with SessionLocal() as session:
        run = IngestionRuns(started_at=started_at, status='pending')
        session.add(run)
        session.commit()
        session.refresh(run)
        return run.id


def complete_ingestion_run(
    run_id: int,
    appearances: list[tuple[int, int, int]],
) -> None:
    """Publish all run appearances and the success marker in one commit."""

    with SessionLocal() as session:
        run = session.get(IngestionRuns, run_id)
        if not run or run.status != 'pending':
            raise ValueError(f"Ingestion run {run_id} is not pending")

        for source_id, article_id, position in appearances:
            session.add(ArticleAppearances(
                run_id=run_id,
                source_id=source_id,
                article_id=article_id,
                position=position,
            ))

        run.status = 'succeeded'
        run.completed_at = datetime.now(timezone.utc)
        session.commit()


def fail_ingestion_run(run_id: int) -> None:
    """Mark a run failed without exposing any of its staged appearances."""

    with SessionLocal() as session:
        run = session.get(IngestionRuns, run_id)
        if run and run.status == 'pending':
            run.status = 'failed'
            run.completed_at = datetime.now(timezone.utc)
            session.commit()


def _get_run_headlines(
    session,
    start: datetime,
    end: datetime,
) -> Optional[list[tuple[str, str, str, Articles]]]:
    """Return the latest successful atomic run, or None for legacy data."""

    if not inspect(engine).has_table(IngestionRuns.__tablename__):
        return None

    first_run_at = session.query(func.min(IngestionRuns.started_at)).scalar()
    run_id = (
        session.query(IngestionRuns.id)
        .filter(
            IngestionRuns.status == 'succeeded',
            IngestionRuns.started_at >= start,
            IngestionRuns.started_at < end,
        )
        .order_by(IngestionRuns.started_at.desc())
        .limit(1)
        .scalar()
    )
    if run_id is None:
        # Preserve the legacy archive before the first run-based edition. On
        # and after the migration date, an empty result means there is no
        # successfully published edition for that day.
        if first_run_at is None or end <= first_run_at:
            return None
        return []

    return (
        session.query(
            Countries.name,
            Sources.name,
            Sources.political_leaning,
            Articles,
        )
        .join(Sources, Sources.country_id == Countries.id)
        .join(
            ArticleAppearances,
            ArticleAppearances.source_id == Sources.id,
        )
        .join(Articles, Articles.id == ArticleAppearances.article_id)
        .filter(ArticleAppearances.run_id == run_id)
        .order_by(Sources.id, ArticleAppearances.position)
        .all()
    )


def get_headlines_by_country(
    target_date: Optional[date] = None
) -> defaultdict[Any, dict[Any, Any]]:
    """
    Returns a dictionary version of the data based on the date the articles
    were captured.

    :param target_date: the target date to filter on
    :return: a list of the original headlines in English
    """

    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    start = datetime.combine(
        target_date,
        datetime.min.time(),
        tzinfo=timezone.utc
    )
    end = start + timedelta(days=1)

    with SessionLocal() as session:
        results = _get_run_headlines(session, start, end)

        # Dates collected before run appearances were introduced retain the
        # old per-source snapshot behavior.
        if results is None:
            latest_per_source = (
                session.query(
                    Articles.source_id,
                    func.max(Articles.captured_at).label(
                        "latest_captured_at"
                    ),
                )
                .filter(
                    Articles.captured_at >= start,
                    Articles.captured_at < end,
                )
                .group_by(Articles.source_id)
                .subquery()
            )

            results = (
                session.query(
                    Countries.name,
                    Sources.name,
                    Sources.political_leaning,
                    Articles,
                )
                .join(Sources, Sources.country_id == Countries.id)
                .join(Articles, Articles.source_id == Sources.id)
                .join(
                    latest_per_source,
                    (Articles.source_id == latest_per_source.c.source_id)
                    & (
                        Articles.captured_at
                        == latest_per_source.c.latest_captured_at
                    ),
                )
                .all()
            )

        output = defaultdict(dict)
        for country_name, source_name, political_leaning, article in results:
            if source_name not in output[country_name]:
                output[country_name][source_name] = {
                    "political_leaning": political_leaning,
                    "articles": [],
                }
            output[country_name][source_name]["articles"].append(
                article.to_dict()
            )

    return output


def get_sources_by_ids(source_ids: list[int]) -> dict[int, dict[str, str]]:
    """
    Returns the outlet and country details for the given source ids. Search
    results carry only a source id, so this resolves the outlet name, its
    country and its political leaning in a single query.

    :param source_ids: the source ids as per Postgres
    :return: a mapping of source id to its outlet, country and leaning
    """

    if not source_ids:
        return {}

    with SessionLocal() as session:
        results = (
            session.query(
                Sources.id,
                Sources.name,
                Sources.political_leaning,
                Countries.name
            )
            .join(Countries, Sources.country_id == Countries.id)
            .filter(Sources.id.in_(set(source_ids)))
            .all()
        )

    return {
        source_id: {
            "outlet": source_name,
            "political_leaning": political_leaning,
            "country": country_name,
        }
        for source_id, source_name, political_leaning, country_name in results
    }
