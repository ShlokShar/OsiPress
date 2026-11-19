from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from cron.ai.service import AIService
from cron.events.config import (
    ANCHOR_WEIGHT,
    CENTROID_RECENT_N,
    HIGH,
    LOW,
    PROMOTE_MIN_ARTICLES,
    PROMOTE_MIN_OUTLETS,
    WINDOW_DAYS,
)
from cron.events.vector_store import EventVectorStore
from shared.models import ArticleEvents, Articles, Countries, Events, MatchLog, Sources, Topics


@dataclass
class ReplayArticle:
    id: int
    source_id: int
    country: str
    fact: dict
    vector: list[float]
    observed_at: datetime


class EventClusterer:
    def __init__(
        self,
        session: Session,
        vectors: EventVectorStore,
        ai_service: AIService,
        run_id: int,
    ) -> None:
        self.session = session
        self.vectors = vectors
        self.ai_service = ai_service
        self.run_id = run_id
        self.created = 0
        self.judged = 0
        self.judge_joined = 0

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        left_values = numpy.array(left, dtype=numpy.float32)
        right_values = numpy.array(right, dtype=numpy.float32)
        denominator = numpy.linalg.norm(left_values) * numpy.linalg.norm(right_values)
        return float(left_values @ right_values / denominator) if denominator else 0.0

    def _candidate_details(self, points) -> tuple[list[dict], dict[int, dict]]:
        ids = [int(point.id) for point in points]
        events = {
            event.id: event
            for event in self.session.execute(
                select(Events).where(Events.id.in_(ids))
            ).scalars()
        }
        details = []
        by_id = {}
        for point in points:
            event = events.get(int(point.id))
            vectors = point.vector if isinstance(point.vector, dict) else {}
            if not event or "anchor" not in vectors or "centroid" not in vectors:
                continue
            facts = self._event_facts(event.id, 3)
            detail = {
                "event_id": event.id,
                "title": event.title,
                "facts": facts,
                "anchor": vectors["anchor"],
                "centroid": vectors["centroid"],
            }
            details.append(detail)
            by_id[event.id] = detail
        return details, by_id

    def _event_facts(self, event_id: int, limit: int | None = None) -> list[dict]:
        statement = (
            select(Countries.name, Articles.neutral_fact)
            .join(Sources, Sources.id == Articles.source_id)
            .join(Countries, Countries.id == Sources.country_id)
            .join(ArticleEvents, ArticleEvents.article_id == Articles.id)
            .where(ArticleEvents.event_id == event_id)
            .order_by(func.coalesce(Articles.published_at, Articles.captured_at).desc())
        )
        if limit:
            statement = statement.limit(limit)
        return [
            {"country": country, "fact": fact["fact"]}
            for country, fact in self.session.execute(statement)
            if fact and fact.get("fact")
        ]

    def _candidate_log(self, details: list[dict], scores: dict[int, float]) -> list[dict]:
        return [
            {
                "event_id": detail["event_id"],
                "title": detail["title"],
                "facts": detail["facts"],
                "score": scores[detail["event_id"]],
            }
            for detail in details
        ]

    def _event_vectors(self, event_id: int) -> list[list[float]]:
        article_ids = list(self.session.execute(
            select(ArticleEvents.article_id)
            .where(ArticleEvents.event_id == event_id)
            .join(Articles, Articles.id == ArticleEvents.article_id)
            .order_by(func.coalesce(Articles.published_at, Articles.captured_at).desc())
            .limit(CENTROID_RECENT_N)
        ).scalars())
        vectors = self.vectors.article_vectors(article_ids)
        return [vectors[article_id] for article_id in article_ids if article_id in vectors]

    def _refresh_event(self, event: Events, observed_at: datetime, anchor: list[float]) -> None:
        article_count, outlet_count = self.session.execute(
            select(
                func.count(ArticleEvents.article_id),
                func.count(func.distinct(Articles.source_id)),
            )
            .join(Articles, Articles.id == ArticleEvents.article_id)
            .where(ArticleEvents.event_id == event.id)
        ).one()
        vectors = self._event_vectors(event.id)
        if not vectors:
            raise ValueError(f"Event {event.id} has no fact vectors")
        event.article_count = article_count
        event.outlet_count = outlet_count
        event.last_seen = max(event.last_seen, observed_at)
        self.vectors.upsert(
            event.id,
            self.vectors.centroid(vectors),
            anchor,
            event.status,
            event.last_seen,
        )

    def _create_event(self, article: ReplayArticle, path: str, score: float | None) -> Events:
        event = Events(
            status="hidden",
            outlet_count=1,
            article_count=1,
            first_seen=article.observed_at,
            last_seen=article.observed_at,
            first_published_at=article.observed_at,
        )
        self.session.add(event)
        self.session.flush()
        self.session.add(ArticleEvents(
            article_id=article.id,
            event_id=event.id,
            joined_at=article.observed_at,
            match_path=path,
            match_score=score,
        ))
        self.session.flush()
        self.vectors.upsert(
            event.id,
            article.vector,
            article.vector,
            event.status,
            event.last_seen,
        )
        self.created += 1
        return event

    def process(self, article: ReplayArticle) -> None:
        points = self.vectors.candidates(article.vector, article.observed_at)
        details, by_id = self._candidate_details(points)
        scores = {
            detail["event_id"]: (
                ANCHOR_WEIGHT * self._cosine(article.vector, detail["anchor"])
                + (1 - ANCHOR_WEIGHT) * self._cosine(article.vector, detail["centroid"])
            )
            for detail in details
        }
        best_id = max(scores, key=scores.get) if scores else None
        best_score = scores[best_id] if best_id is not None else None
        path = "low"
        event = None
        if best_score is not None and best_score >= HIGH:
            path = "high"
            event = self.session.get(Events, best_id)
        elif best_score is not None and best_score >= LOW:
            path = "judge"
            self.judged += 1
            selected = self.ai_service.judge_event(
                article.fact["fact"],
                [
                    {
                        "event_id": detail["event_id"],
                        "title": detail["title"],
                        "facts": detail["facts"],
                    }
                    for detail in details[:3]
                ],
            )
            if selected in by_id:
                event = self.session.get(Events, selected)
                self.judge_joined += 1
        if event is None:
            event = self._create_event(article, path, best_score)
        else:
            self.session.add(ArticleEvents(
                article_id=article.id,
                event_id=event.id,
                joined_at=article.observed_at,
                match_path=path,
                match_score=best_score,
            ))
            self.session.flush()
            self._refresh_event(event, article.observed_at, by_id[event.id]["anchor"])
        self.session.add(MatchLog(
            run_id=self.run_id,
            article_id=article.id,
            candidates=self._candidate_log(details, scores),
            decision=str(event.id),
            path=path,
            created_at=datetime.now(timezone.utc),
        ))

    def finalize(self) -> dict:
        promoted = []
        events = self.session.execute(
            select(Events).where(Events.status == "hidden")
        ).scalars()
        for event in events:
            if event.article_count < PROMOTE_MIN_ARTICLES or event.outlet_count < PROMOTE_MIN_OUTLETS:
                continue
            event.status = "visible"
            promoted.append(event.id)
        self.session.flush()
        self.vectors.set_status(promoted, "visible")
        self._title_events()
        cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
        expired = list(self.session.execute(
            select(Events.id).where(
                Events.status == "hidden",
                Events.last_seen < cutoff,
            )
        ).scalars())
        if expired:
            self.session.execute(delete(ArticleEvents).where(ArticleEvents.event_id.in_(expired)))
            self.session.execute(delete(Events).where(Events.id.in_(expired)))
            self.vectors.delete(expired)
        return {"created": self.created, "promoted": len(promoted), "expired": len(expired), "judge_calls": self.judged, "judge_joined": self.judge_joined}

    def _title_events(self) -> None:
        topics = [
            {"id": topic.id, "name": topic.name, "description": topic.description}
            for topic in self.session.execute(select(Topics)).scalars()
        ]
        topic_ids = {topic["id"] for topic in topics}
        events = self.session.execute(
            select(Events).where(Events.status == "visible", Events.title.is_(None))
        ).scalars()
        for event in events:
            facts = self._event_facts(event.id)
            if len({fact["country"] for fact in facts}) < 2:
                continue
            result = self.ai_service.title_event(facts, topics)
            event.title = result.title
            event.topic_id = result.topic_id if result.topic_id in topic_ids else None
            event.titled_at = datetime.now(timezone.utc)

    def visible_cross_country_events(self) -> list[Events]:
        events = self.session.execute(
            select(Events).where(Events.status == "visible")
        ).scalars()
        output = []
        for event in events:
            countries = self.session.execute(
                select(func.count(func.distinct(Countries.id)))
                .join(Sources, Sources.country_id == Countries.id)
                .join(Articles, Articles.source_id == Sources.id)
                .join(ArticleEvents, ArticleEvents.article_id == Articles.id)
                .where(ArticleEvents.event_id == event.id)
            ).scalar_one()
            if countries >= 2:
                output.append(event)
        return output
