
from collections import defaultdict
import hashlib
import os
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    func,
    String,
    Text,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (
    Mapped,
    mapped_column
)
from sqlalchemy.dialects.postgresql import insert

from shared.database import (
    Base,
    SessionLocal,
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
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    neutral_fact: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
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


class SeenItems(Base):
    __tablename__ = 'seen_items'

    outlet_id: Mapped[int] = mapped_column(ForeignKey('sources.id'), primary_key=True)
    guid: Mapped[str] = mapped_column(Text, primary_key=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OutletRunLog(Base):
    __tablename__ = 'outlet_run_log'

    run_id: Mapped[int] = mapped_column(ForeignKey('ingestion_runs.id'), primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey('sources.id'), primary_key=True)
    feed_size: Mapped[int] = mapped_column(Integer, default=0)
    new_items: Mapped[int] = mapped_column(Integer, default=0)
    political: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    skipped_by_cap: Mapped[int] = mapped_column(Integer, default=0)
    gap: Mapped[bool] = mapped_column(default=False)
    cheap_pass_calls: Mapped[int] = mapped_column(Integer, default=0)
    full_pass_calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class PendingItem(Base):
    __tablename__ = 'pending_items'

    outlet_id: Mapped[int] = mapped_column(ForeignKey('sources.id'), primary_key=True)
    guid: Mapped[str] = mapped_column(Text, primary_key=True)
    article_id: Mapped[Optional[int]] = mapped_column(ForeignKey('articles.id'))
    run_id: Mapped[int] = mapped_column(ForeignKey('ingestion_runs.id'))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    link: Mapped[str] = mapped_column(Text)
    headline: Mapped[str] = mapped_column(Text)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    political: Mapped[bool] = mapped_column(default=False, server_default=text('false'))


def get_seen_items(outlet_id: int, guids: list[str]) -> tuple[set[str], bool]:
    with SessionLocal() as session:
        matched, count = session.query(
            func.array_agg(SeenItems.guid).filter(SeenItems.guid.in_(guids)),
            func.count(),
        ).filter(
            SeenItems.outlet_id == outlet_id,
        ).one()
        return set(matched or []), count > 0


def get_feed_pending(outlet_id: int, guids: set[str]):
    with SessionLocal() as session:
        return {item.guid: item for item in session.query(PendingItem).filter(
            PendingItem.outlet_id == outlet_id, PendingItem.guid.in_(guids)
        ).all()}


def get_pending_items(outlet_id: int, excluded_guids: set[str]):
    minimum = datetime.min.replace(tzinfo=timezone.utc)
    published = func.coalesce(PendingItem.published_at, minimum)
    cursor = None
    while True:
        with SessionLocal() as session:
            query = session.query(PendingItem).filter(
                PendingItem.outlet_id == outlet_id,
                PendingItem.guid.notin_(excluded_guids),
            )
            if cursor is not None:
                last_time, last_guid = cursor
                query = query.filter((published < last_time) |
                                     ((published == last_time) & (PendingItem.guid > last_guid)))
            batch = query.order_by(published.desc(), PendingItem.guid).limit(100).all()
        if not batch:
            return
        last = batch[-1]
        cursor = (last.published_at or minimum, last.guid)
        yield from batch


def queue_item(outlet_id, guid, run_id, first_seen, link, headline, published_at):
    with SessionLocal() as session:
        session.execute(insert(PendingItem).values(
            outlet_id=outlet_id, guid=guid, run_id=run_id, first_seen=first_seen,
            link=link, headline=headline, published_at=published_at, political=False,
        ).on_conflict_do_nothing())
        session.commit()


def mark_pending_political(outlet_id, guid):
    with SessionLocal() as session:
        pending = session.get(PendingItem, (outlet_id, guid))
        pending.political = True
        session.commit()


def mark_item_seen(outlet_id: int, guid: str, first_seen: datetime) -> None:
    with SessionLocal() as session:
        session.execute(
            insert(SeenItems).values(outlet_id=outlet_id, guid=guid, first_seen=first_seen)
            .on_conflict_do_nothing()
        )
        session.commit()


def stage_pending_item(outlet_id: int, guid: str, article_id: int, run_id: int, first_seen: datetime) -> None:
    with SessionLocal() as session:
        pending = session.get(PendingItem, (outlet_id, guid))
        pending.run_id = run_id
        pending.article_id = article_id
        session.commit()


def stage_appearance(run_id: int, outlet_id: int, article_id: int, position: int) -> bool:
    with SessionLocal() as session:
        result = session.execute(
            insert(ArticleAppearances).values(run_id=run_id, source_id=outlet_id,
                                              article_id=article_id, position=position)
            .on_conflict_do_nothing()
        )
        session.commit()
        return result.rowcount > 0


def complete_pending_item(outlet_id: int, guid: str) -> None:
    with SessionLocal() as session:
        pending = session.get(PendingItem, (outlet_id, guid))
        if pending:
            session.execute(insert(SeenItems).values(outlet_id=outlet_id, guid=guid,
                                                    first_seen=pending.first_seen)
                            .on_conflict_do_nothing())
            session.delete(pending)
            session.commit()


def save_outlet_run_log(log: OutletRunLog) -> bool:
    with SessionLocal() as session:
        session.add(log)
        session.flush()
        recent = (
            session.query(OutletRunLog.skipped_by_cap)
            .join(IngestionRuns, IngestionRuns.id == OutletRunLog.run_id)
            .filter(OutletRunLog.outlet_id == log.outlet_id)
            .order_by(IngestionRuns.started_at.desc(), IngestionRuns.id.desc())
            .limit(3).all()
        )
        session.commit()
        return len(recent) == 3 and all(count > 0 for (count,) in recent)


def add_outlet_token_usage(run_id: int, outlet_id: int, input_tokens: int, output_tokens: int) -> None:
    with SessionLocal() as session:
        log = session.get(OutletRunLog, (run_id, outlet_id))
        if log:
            log.input_tokens = (log.input_tokens or 0) + input_tokens
            log.output_tokens = (log.output_tokens or 0) + output_tokens
            session.commit()


class Topics(Base):
    __tablename__ = 'topics'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    description: Mapped[str] = mapped_column()


class Events(Base):
    __tablename__ = 'events'

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey('topics.id'),
        nullable=True,
    )
    title: Mapped[Optional[str]] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column()
    outlet_count: Mapped[int] = mapped_column(Integer, default=0)
    article_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    titled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint("status IN ('hidden', 'visible')"),
    )


class ArticleEvents(Base):
    __tablename__ = 'article_events'

    article_id: Mapped[int] = mapped_column(
        ForeignKey('articles.id'),
        primary_key=True,
    )
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id'))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    match_path: Mapped[str] = mapped_column()
    match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    __table_args__ = (
        CheckConstraint("match_path IN ('high', 'low', 'judge')"),
    )


class MatchLog(Base):
    __tablename__ = 'match_log'

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey('ingestion_runs.id'),
        nullable=True,
    )
    article_id: Mapped[int] = mapped_column(ForeignKey('articles.id'))
    candidates: Mapped[dict] = mapped_column(JSONB)
    decision: Mapped[str] = mapped_column()
    path: Mapped[str] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("path IN ('high', 'low', 'judge')"),
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


def add_canonical_article(article: Articles, normalized_url: str, pending: Optional[dict] = None) -> Articles:
    """Save a processed article and claim its normalized URL atomically."""

    url_hash = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()
    with SessionLocal() as session:
        try:
            session.add(article)
            session.flush()
            session.add(ArticleURLs(
                url_hash=url_hash,
                url=normalized_url,
                article_id=article.id,
            ))
            if pending is not None:
                queued = session.get(PendingItem, (pending['outlet_id'], pending['guid']))
                queued.article_id = article.id
                queued.run_id = pending['run_id']
            session.commit()
        except IntegrityError:
            # Another ingestion worker may have claimed this normalized URL
            # between find_article_by_url() and this insert. Its transaction
            # wins; return that canonical article rather than failing the run.
            session.rollback()
            article = (
                session.query(Articles)
                .join(ArticleURLs, ArticleURLs.article_id == Articles.id)
                .filter(
                    ArticleURLs.url_hash == url_hash,
                    ArticleURLs.url == normalized_url,
                )
                .first()
            )
            if article is None:
                raise

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
) -> bool:
    """Publish a nonempty run, keeping empty runs out of the edition history."""

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

        session.flush()
        has_appearances = session.query(ArticleAppearances.run_id).filter_by(run_id=run_id).first() is not None
        run.status = 'succeeded' if has_appearances else 'no_updates'
        run.completed_at = datetime.now(timezone.utc)
        session.commit()
        return has_appearances


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

    first_run_at = session.query(func.min(IngestionRuns.started_at)).scalar()
    run_id = (
        session.query(IngestionRuns.id)
        .filter(
            IngestionRuns.status == 'succeeded',
            IngestionRuns.started_at >= start,
            IngestionRuns.started_at < end,
        )
        .order_by(IngestionRuns.started_at.desc(), IngestionRuns.id.desc())
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


def get_visible_events() -> list[dict[str, Any]]:
    """Return visible cross-country events with their newest coverage."""

    country_order = {"Iran": 0, "Israel": 1}
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)

    with SessionLocal() as session:
        sources_by_country = defaultdict(list)
        for country, source in (
            session.query(Countries.name, Sources)
            .join(Sources, Sources.country_id == Countries.id)
            .order_by(Countries.name, Sources.name)
            .all()
        ):
            sources_by_country[country].append({
                "id": source.id,
                "name": source.name,
            })

        filters = [Events.status == "visible"]
        if os.getenv("EVENTS_INCLUDE_HISTORY") != "1":
            filters.append(Events.last_seen >= cutoff)
        events = (
            session.query(Events)
            .filter(*filters)
            .order_by(Events.last_seen.desc())
            .all()
        )
        if not events:
            return []

        topics = {
            topic.id: topic.name
            for topic in session.query(Topics).all()
        }
        event_ids = [event.id for event in events]
        members_by_event = defaultdict(list)
        for event_id, joined_at, article, source, country in (
            session.query(
                ArticleEvents.event_id,
                ArticleEvents.joined_at,
                Articles,
                Sources,
                Countries.name,
            )
            .join(Articles, Articles.id == ArticleEvents.article_id)
            .join(Sources, Sources.id == Articles.source_id)
            .join(Countries, Countries.id == Sources.country_id)
            .filter(ArticleEvents.event_id.in_(event_ids))
            .order_by(
                ArticleEvents.event_id,
                func.coalesce(Articles.published_at, Articles.captured_at).desc(),
            )
            .all()
        ):
            members_by_event[event_id].append({
                "country": country,
                "source_id": source.id,
                "source": source.name,
                "leaning": source.political_leaning,
                "headline": article.headline,
                "translated_headline": article.translated_headline,
                "link": article.link,
                "published_at": article.published_at or article.captured_at,
                "joined_at": joined_at,
            })

    output = []
    for event in events:
        members = members_by_event[event.id]
        countries = {member["country"] for member in members}
        if len(countries) < 2:
            continue

        grouped = defaultdict(list)
        recent_articles = 0
        recent_sources = set()
        for member in members:
            grouped[member["country"]].append(member)
            if member["joined_at"] >= cutoff:
                recent_articles += 1
                recent_sources.add(member["source_id"])

        coverage = []
        for country, articles in grouped.items():
            newest = articles[:3]
            covered = {article["source_id"] for article in articles}
            coverage.append({
                "country": country,
                "articles": newest,
                "more_count": max(0, len(articles) - len(newest)),
                "sources": [
                    {**source, "covered": source["id"] in covered}
                    for source in sources_by_country[country]
                ],
            })
        coverage.sort(key=lambda item: (country_order.get(item["country"], 99), item["country"]))

        output.append({
            "id": event.id,
            "title": event.title or "Coverage event",
            "topic": topics.get(event.topic_id),
            "first_published_at": event.first_published_at,
            "last_seen": event.last_seen,
            "article_count": event.article_count,
            "outlet_count": event.outlet_count,
            "countries": coverage,
            "recent_activity": recent_articles + len(recent_sources),
        })

    return sorted(
        output,
        key=lambda event: (event["recent_activity"], event["last_seen"]),
        reverse=True,
    )


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


def _event_members(session, event_ids: list[int], before: Optional[datetime] = None) -> defaultdict[int, list[dict]]:
    """Return every article in each event, newest first, with its outlet."""

    members: defaultdict[int, list[dict]] = defaultdict(list)
    if not event_ids:
        return members

    query = (
        session.query(
            ArticleEvents.event_id,
            Articles,
            Sources,
            Countries.name,
        )
        .join(Articles, Articles.id == ArticleEvents.article_id)
        .join(Sources, Sources.id == Articles.source_id)
        .join(Countries, Countries.id == Sources.country_id)
        .filter(ArticleEvents.event_id.in_(event_ids))
    )
    if before is not None:
        query = query.filter(
            ArticleEvents.joined_at < before,
            Articles.captured_at < before,
        )
    rows = (
        query
        .order_by(
            ArticleEvents.event_id,
            func.coalesce(
                Articles.published_at, Articles.captured_at
            ).desc().nullslast(),
        )
        .all()
    )

    for event_id, article, source, country_name in rows:
        members[event_id].append({
            "article_id": article.id,
            "country": country_name,
            "outlet": source.name,
            "outlet_id": source.id,
            "leaning": source.political_leaning,
            "headline": article.headline,
            "translated_headline": article.translated_headline,
            "summary": article.summary,
            "references_original": list(article.references_original or []),
            "references_translated": list(article.references_translated or []),
            "link": article.link,
            "published_at": article.published_at,
            "captured_at": article.captured_at,
        })

    return members


def _event_payload(event: Events, topics: dict[int, str], members: list[dict]):
    return {
        "id": event.id,
        "title": event.title or "Coverage event",
        "topic": topics.get(event.topic_id),
        "status": event.status,
        "first_published_at": event.first_published_at,
        "first_seen": event.first_seen,
        "last_seen": event.last_seen,
        "article_count": event.article_count,
        "outlet_count": event.outlet_count,
        "articles": members,
    }


def get_events_for_day(
    target_date: Optional[date] = None,
    fallback_days: int = 3,
) -> tuple[Optional[date], list[dict]]:
    """Return one day's visible events with all of their coverage.

    Unlike `get_visible_events`, which keeps a rolling 24-hour window for the
    old Top stories page, this is anchored to a calendar day so the Today and
    Archive pages agree on what "today" holds. Days with no published edition
    fall back up to `fallback_days` earlier, the same way `all_today` does.
    """

    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    with SessionLocal() as session:
        topics = {topic.id: topic.name for topic in session.query(Topics).all()}

        for offset in range(fallback_days + 1):
            day = target_date - timedelta(days=offset)
            start = datetime.combine(
                day, datetime.min.time(), tzinfo=timezone.utc
            )
            end = start + timedelta(days=1)

            events = (
                session.query(Events)
                .join(ArticleEvents, ArticleEvents.event_id == Events.id)
                .join(ArticleAppearances, ArticleAppearances.article_id == ArticleEvents.article_id)
                .join(IngestionRuns, IngestionRuns.id == ArticleAppearances.run_id)
                .filter(
                    Events.status == "visible",
                    IngestionRuns.status == "succeeded",
                    IngestionRuns.started_at >= start,
                    IngestionRuns.started_at < end,
                )
                .distinct()
                .order_by(Events.last_seen.desc())
                .all()
            )
            if not events:
                continue

            members = _event_members(session, [event.id for event in events], before=end)
            latest_run_id = (
                session.query(IngestionRuns.id)
                .filter(IngestionRuns.status == "succeeded",
                        IngestionRuns.started_at >= start,
                        IngestionRuns.started_at < end)
                .order_by(IngestionRuns.started_at.desc())
                .limit(1).scalar()
            )
            latest_articles = {
                article_id for (article_id,) in session.query(ArticleAppearances.article_id)
                .filter(ArticleAppearances.run_id == latest_run_id).all()
            }
            for rows in members.values():
                for row in rows:
                    row["latest_run"] = row["article_id"] in latest_articles
            payloads = [
                _event_payload(event, topics, members[event.id])
                for event in events
                if len({row["country"] for row in members[event.id]}) >= 2
            ]
            if payloads:
                return day, payloads

    return None, []


def get_event_by_id(event_id: int) -> Optional[dict]:
    """Return one visible event with all of its coverage."""

    with SessionLocal() as session:
        event = (
            session.query(Events)
            .filter(Events.id == event_id, Events.status == "visible")
            .first()
        )
        if not event:
            return None

        topics = {topic.id: topic.name for topic in session.query(Topics).all()}
        members = _event_members(session, [event.id])
        if not members[event.id]:
            return None

        return _event_payload(event, topics, members[event.id])


def _observed_at():
    """The column the archive counts by: publication time, else capture."""

    return func.coalesce(Articles.published_at, Articles.captured_at)


def get_archive_daily_counts(
    start: date,
    end: date,
) -> dict[tuple[str, str], int]:
    """Return article counts keyed by (ISO day, country name)."""

    window_start = datetime.combine(
        start, datetime.min.time(), tzinfo=timezone.utc
    )
    window_end = datetime.combine(
        end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
    )
    with SessionLocal() as session:
        run_day = func.date(func.timezone("UTC", IngestionRuns.started_at))
        latest_runs = (
            session.query(
                IngestionRuns.id.label("id"),
                run_day.label("day"),
                func.row_number().over(
                    partition_by=run_day,
                    order_by=(IngestionRuns.started_at.desc(), IngestionRuns.id.desc()),
                ).label("rank"),
            )
            .filter(IngestionRuns.status == "succeeded",
                    IngestionRuns.started_at >= window_start,
                    IngestionRuns.started_at < window_end)
            .subquery()
        )
        rows = (
            session.query(
                latest_runs.c.day,
                Countries.name,
                func.count(ArticleAppearances.article_id),
            )
            .select_from(latest_runs)
            .join(ArticleAppearances, ArticleAppearances.run_id == latest_runs.c.id)
            .join(Sources, Sources.id == ArticleAppearances.source_id)
            .join(Countries, Countries.id == Sources.country_id)
            .filter(latest_runs.c.rank == 1)
            .group_by(latest_runs.c.day, Countries.name)
            .all()
        )
        first_run = session.query(func.min(IngestionRuns.started_at)).scalar()
        legacy_end = min(window_end, first_run.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)) if first_run else window_end
        if legacy_end > window_start:
            captured_day = func.date(func.timezone("UTC", Articles.captured_at))
            latest = (
                session.query(Articles.source_id.label("source_id"), captured_day.label("day"),
                              func.max(Articles.captured_at).label("captured_at"))
                .filter(Articles.captured_at >= window_start, Articles.captured_at < legacy_end)
                .group_by(Articles.source_id, captured_day)
                .subquery()
            )
            rows += (
                session.query(latest.c.day, Countries.name, func.count(Articles.id))
                .select_from(latest)
                .join(Articles, (Articles.source_id == latest.c.source_id) &
                      (Articles.captured_at == latest.c.captured_at))
                .join(Sources, Sources.id == Articles.source_id)
                .join(Countries, Countries.id == Sources.country_id)
                .group_by(latest.c.day, Countries.name).all()
            )

    return {
        (day.isoformat() if hasattr(day, "isoformat") else str(day), country):
            count
        for day, country, count in rows
    }


def get_archive_events(start: date, end: date) -> list[dict]:
    """Return visible event coverage for each UTC day in the range."""

    grouped = {}
    with SessionLocal() as session:
        first_run = session.query(func.min(IngestionRuns.started_at)).scalar()
        window_start = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
        window_end = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        legacy_end = (first_run.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                      if first_run else window_end)

        def consume(query):
            for day, event_id, title, topic, article_id, outlet, leaning, country in query.yield_per(100):
                item = grouped.setdefault((day, event_id), {
                    "id": event_id, "title": title or "Coverage event",
                    "topic": topic, "day": day, "articles": {},
                })
                item["articles"][article_id] = {
                    "article_id": article_id, "country": country,
                    "outlet": outlet, "leaning": leaning,
                }

        batch_start = window_start
        while batch_start < window_end:
            batch_end = min(batch_start + timedelta(days=30), window_end)
            run_day = func.date(func.timezone("UTC", IngestionRuns.started_at))
            if batch_end > legacy_end:
                query = (
                    session.query(run_day, Events.id, Events.title, Topics.name,
                                  Articles.id, Sources.name, Sources.political_leaning, Countries.name)
                    .select_from(IngestionRuns)
                    .join(ArticleAppearances, ArticleAppearances.run_id == IngestionRuns.id)
                    .join(Articles, Articles.id == ArticleAppearances.article_id)
                    .join(ArticleEvents, ArticleEvents.article_id == Articles.id)
                    .join(Events, Events.id == ArticleEvents.event_id)
                    .join(Sources, Sources.id == Articles.source_id)
                    .join(Countries, Countries.id == Sources.country_id)
                    .outerjoin(Topics, Topics.id == Events.topic_id)
                    .filter(Events.status == "visible", IngestionRuns.status == "succeeded",
                            IngestionRuns.started_at >= max(batch_start, legacy_end),
                            IngestionRuns.started_at < batch_end)
                )
                consume(query)
            if batch_start < legacy_end:
                captured_day = func.date(func.timezone("UTC", Articles.captured_at))
                latest = (
                    session.query(Articles.source_id.label("source_id"), captured_day.label("day"),
                                  func.max(Articles.captured_at).label("captured_at"))
                    .filter(Articles.captured_at >= batch_start,
                            Articles.captured_at < min(batch_end, legacy_end))
                    .group_by(Articles.source_id, captured_day).subquery()
                )
                query = (
                    session.query(latest.c.day, Events.id, Events.title, Topics.name,
                                  Articles.id, Sources.name, Sources.political_leaning, Countries.name)
                    .select_from(latest)
                    .join(Articles, (Articles.source_id == latest.c.source_id) &
                          (Articles.captured_at == latest.c.captured_at))
                    .join(ArticleEvents, ArticleEvents.article_id == Articles.id)
                    .join(Events, Events.id == ArticleEvents.event_id)
                    .join(Sources, Sources.id == Articles.source_id)
                    .join(Countries, Countries.id == Sources.country_id)
                    .outerjoin(Topics, Topics.id == Events.topic_id)
                    .filter(Events.status == "visible")
                )
                consume(query)
            batch_start = batch_end

    output = []
    for item in grouped.values():
        item["articles"] = list(item["articles"].values())
        by_country = defaultdict(list)
        for row in item["articles"]:
            by_country[row["country"]].append(row)
        item["by_country"] = dict(by_country)
        output.append(item)
    return output


def get_edition_count(start: date, end: date) -> int:
    """Return how many ingestion runs published successfully in a window."""

    window_start = datetime.combine(
        start, datetime.min.time(), tzinfo=timezone.utc
    )
    window_end = datetime.combine(
        end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
    )

    with SessionLocal() as session:
        return (
            session.query(func.count(IngestionRuns.id))
            .filter(
                IngestionRuns.status == "succeeded",
                IngestionRuns.started_at >= window_start,
                IngestionRuns.started_at < window_end,
            )
            .scalar()
        ) or 0


def find_articles(query: str, limit: int = 500) -> list[dict]:
    """Return every article matching a query, newest first.

    This is the Search page's own query, not the hybrid relevance path in
    `shared.search_service`. The page needs exact totals, a date range and
    per-outlet counts including outlets with no match, which a top-k ranking
    cannot provide, and it has to match the original-language headline, the
    outlet name and the event title as well as the translation.
    """

    needle = (query or "").strip()
    if not needle:
        return []

    pattern = f"%{needle}%"
    observed = _observed_at()
    with SessionLocal() as session:
        rows = (
            session.query(
                Articles,
                Sources,
                Countries.name,
                Events.title,
            )
            .join(Sources, Sources.id == Articles.source_id)
            .join(Countries, Countries.id == Sources.country_id)
            .outerjoin(ArticleEvents, ArticleEvents.article_id == Articles.id)
            .outerjoin(Events, Events.id == ArticleEvents.event_id)
            .filter(
                Articles.translated_headline.ilike(pattern)
                | Articles.headline.ilike(pattern)
                | Sources.name.ilike(pattern)
                | Events.title.ilike(pattern)
            )
            .order_by(observed.desc().nullslast(), Articles.id.desc())
            .limit(limit)
            .all()
        )

    return [
        {
            "article_id": article.id,
            "country": country_name,
            "outlet": source.name,
            "outlet_id": source.id,
            "leaning": source.political_leaning,
            "headline": article.headline,
            "translated_headline": article.translated_headline,
            "link": article.link,
            "published_at": article.published_at,
            "captured_at": article.captured_at,
            "event_title": event_title,
        }
        for article, source, country_name, event_title in rows
    ]


def get_outlets_by_country() -> defaultdict[str, list[dict]]:
    """Return every outlet grouped by its country's English name."""

    with SessionLocal() as session:
        rows = (
            session.query(Countries.name, Sources)
            .join(Sources, Sources.country_id == Countries.id)
            .order_by(Countries.name, Sources.name)
            .all()
        )

    output: defaultdict[str, list[dict]] = defaultdict(list)
    for country_name, source in rows:
        output[country_name].append({
            "id": source.id,
            "outlet": source.name,
            "leaning": source.political_leaning,
            "link": source.link,
        })
    return output


def get_latest_headline_by_outlet(
    target_date: Optional[date] = None,
    fallback_days: int = 3,
) -> dict[int, dict]:
    """Return each outlet's newest article on the most recent covered day."""

    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    with SessionLocal() as session:
        for offset in range(fallback_days + 1):
            day = target_date - timedelta(days=offset)
            start = datetime.combine(
                day, datetime.min.time(), tzinfo=timezone.utc
            )
            end = start + timedelta(days=1)

            rows = _get_run_headlines(session, start, end)
            if rows is None:
                rows = (
                    session.query(Countries.name, Sources.name, Sources.political_leaning, Articles)
                    .join(Sources, Sources.country_id == Countries.id)
                    .join(Articles, Articles.source_id == Sources.id)
                    .filter(Articles.captured_at >= start, Articles.captured_at < end)
                    .order_by(Articles.captured_at.desc())
                    .all()
                )
            if not rows:
                continue

            newest: dict[int, dict] = {}
            for country_name, source_name, leaning, article in rows:
                if article.source_id in newest:
                    continue
                newest[article.source_id] = {
                    "article_id": article.id,
                    "country": country_name,
                    "outlet": source_name,
                    "outlet_id": article.source_id,
                    "leaning": leaning,
                    "headline": article.headline,
                    "translated_headline": article.translated_headline,
                    "link": article.link,
                    "published_at": article.published_at,
                    "captured_at": article.captured_at,
                }
            if newest:
                return newest

    return {}


def get_day_articles(
    target_date: Optional[date] = None,
    fallback_days: int = 3,
) -> tuple[Optional[date], list[dict]]:
    """Return every article observed on a day, newest first.

    This feeds the All today view, which lists each outlet's coverage without
    grouping it into events.
    """

    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    with SessionLocal() as session:
        for offset in range(fallback_days + 1):
            day = target_date - timedelta(days=offset)
            start = datetime.combine(
                day, datetime.min.time(), tzinfo=timezone.utc
            )
            end = start + timedelta(days=1)

            rows = _get_run_headlines(session, start, end)
            if rows is None:
                rows = (
                    session.query(Countries.name, Sources.name, Sources.political_leaning, Articles)
                    .join(Sources, Sources.country_id == Countries.id)
                    .join(Articles, Articles.source_id == Sources.id)
                    .filter(Articles.captured_at >= start, Articles.captured_at < end)
                    .order_by(Articles.captured_at.desc())
                    .all()
                )
            if not rows:
                continue

            return day, [
                {
                    "article_id": article.id,
                    "country": country_name,
                    "outlet": source_name,
                    "outlet_id": article.source_id,
                    "leaning": leaning,
                    "headline": article.headline,
                    "translated_headline": article.translated_headline,
                    "summary": article.summary,
                    "references_original": list(
                        article.references_original or []
                    ),
                    "references_translated": list(
                        article.references_translated or []
                    ),
                    "link": article.link,
                    "published_at": article.published_at,
                    "captured_at": article.captured_at,
                }
                for country_name, source_name, leaning, article in rows
            ]

    return None, []


def get_latest_run(target_date: Optional[date] = None) -> Optional[dict]:
    """Return the newest successful ingestion run on a day."""

    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    end = datetime.combine(
        target_date + timedelta(days=1), datetime.min.time(),
        tzinfo=timezone.utc,
    )
    start = end - timedelta(days=1)

    with SessionLocal() as session:
        run = (
            session.query(IngestionRuns)
            .filter(
                IngestionRuns.status == "succeeded",
                IngestionRuns.started_at >= start,
                IngestionRuns.started_at < end,
            )
            .order_by(IngestionRuns.started_at.desc())
            .first()
        )
        if not run:
            return None
        return {
            "id": run.id,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
        }


def get_topic_names() -> list[str]:
    """Return every topic name, for the search page's suggestions."""

    with SessionLocal() as session:
        return [
            name for (name,) in
            session.query(Topics.name).order_by(Topics.name).all()
        ]
