import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, func, select

from cron.ai.service import AIService
from cron.events.cluster import EventClusterer, ReplayArticle
from cron.events.config import EVAL_COLLECTION
from cron.events.vector_store import EventVectorStore
from shared.database import DATABASE_URL, session_factory
from shared.models import ArticleEvents, Articles, Countries, Events, IngestionRuns, MatchLog, Sources


BATCH_SIZE = 100
DEFAULT_REPORT = Path("evals/results/event_replay.json")
DEFAULT_LABELS = Path("evals/golden/event_labels.json")


def clear_events(session) -> None:
    session.execute(delete(MatchLog))
    session.execute(delete(ArticleEvents))
    session.execute(delete(Events))
    session.commit()


def article_rows(session):
    statement = (
        select(
            Articles.id,
            Articles.source_id,
            Countries.name,
            Articles.neutral_fact,
            func.coalesce(Articles.published_at, Articles.captured_at).label("observed_at"),
        )
        .join(Sources, Sources.id == Articles.source_id)
        .join(Countries, Countries.id == Sources.country_id)
        .where(Articles.neutral_fact.is_not(None))
        .order_by(func.coalesce(Articles.published_at, Articles.captured_at), Articles.id)
        .execution_options(yield_per=BATCH_SIZE)
    )
    return session.execute(statement).partitions(BATCH_SIZE)


def histogram(values: list[float]) -> dict[str, int]:
    buckets = Counter()
    for value in values:
        lower = int(value * 10) / 10
        buckets[f"{lower:.1f}-{lower + 0.1:.1f}"] += 1
    return dict(sorted(buckets.items()))


def report(session, clusterer: EventClusterer, summary: dict) -> dict:
    visible = clusterer.visible_cross_country_events()
    by_day = Counter(event.first_published_at.date().isoformat() for event in visible)
    daily_counts = list(by_day.values())
    scores = list(session.execute(
        select(ArticleEvents.match_score, ArticleEvents.event_id)
        .where(ArticleEvents.match_score.is_not(None))
    ))
    countries = {
        event.id: session.execute(
            select(func.count(func.distinct(Countries.id)))
            .join(Sources, Sources.country_id == Countries.id)
            .join(Articles, Articles.source_id == Sources.id)
            .join(ArticleEvents, ArticleEvents.article_id == Articles.id)
            .where(ArticleEvents.event_id == event.id)
        ).scalar_one()
        for event in session.execute(select(Events)).scalars()
    }
    same = [score for score, event_id in scores if countries[event_id] < 2]
    cross = [score for score, event_id in scores if countries[event_id] >= 2]
    largest = session.execute(
        select(Events).order_by(Events.article_count.desc(), Events.id).limit(10)
    ).scalars()
    output = {
        **summary,
        "visible_both_country": len(visible),
        "visible_cross_country_per_day": {
            "mean": sum(daily_counts) / len(daily_counts) if daily_counts else 0,
            "median": sorted(daily_counts)[len(daily_counts) // 2] if daily_counts else 0,
            "min": min(daily_counts) if daily_counts else 0,
            "max": max(daily_counts) if daily_counts else 0,
        },
        "same_country_score_histogram": histogram(same),
        "cross_country_score_histogram": histogram(cross),
        "largest_events": [
            {
                "event_id": event.id,
                "article_count": event.article_count,
                "outlet_count": event.outlet_count,
                "title": event.title,
                "facts": clusterer._event_facts(event.id),
            }
            for event in largest
        ],
    }
    return output


def export_labels(session, run_id: int) -> list[dict]:
    records = session.execute(
        select(MatchLog, Countries.name, Sources.name, Articles.neutral_fact)
        .join(Articles, Articles.id == MatchLog.article_id)
        .join(Sources, Sources.id == Articles.source_id)
        .join(Countries, Countries.id == Sources.country_id)
        .where(MatchLog.run_id == run_id)
        .order_by(MatchLog.id)
    ).all()
    groups = {"judge": [], "high": [], "low": []}
    for log, country, source, article_fact in records:
        groups[log.path].append({
            "match_log_id": log.id,
            "article_id": log.article_id,
            "country": country,
            "source": source,
            "article_fact": (article_fact or {}).get("fact"),
            "candidates": log.candidates,
            "decision": log.decision,
            "path": log.path,
            "correct": "",
        })
    cross = []
    for record in groups["high"]:
        event_id = int(record["decision"])
        countries = session.execute(
            select(func.count(func.distinct(Countries.id)))
            .join(Sources, Sources.country_id == Countries.id)
            .join(Articles, Articles.source_id == Sources.id)
            .join(ArticleEvents, ArticleEvents.article_id == Articles.id)
            .where(ArticleEvents.event_id == event_id)
        ).scalar_one()
        if countries >= 2:
            cross.append(record)
    cross = cross[:50]
    cross_ids = {record["match_log_id"] for record in cross}
    high = [record for record in groups["high"] if record["match_log_id"] not in cross_ids]
    return groups["judge"][:50] + cross + high[:25] + groups["low"][:25]


def run(database_url: str, reset: bool, report_path: Path, labels_path: Path) -> dict:
    if database_url == DATABASE_URL:
        raise ValueError("Replay requires an isolated database URL")
    sessions = session_factory(database_url)
    vectors = EventVectorStore(EVAL_COLLECTION)
    with sessions() as session:
        existing = session.execute(select(func.count()).select_from(Events)).scalar_one()
        if existing and not reset:
            raise ValueError("Replay target has events; rerun with --reset")
        if reset or not existing:
            clear_events(session)
            vectors.reset()
        run = IngestionRuns(started_at=datetime.now(timezone.utc), status="pending")
        session.add(run)
        session.commit()
        session.refresh(run)
        clusterer = EventClusterer(session, vectors, AIService(), run.id)
        skipped = 0
        try:
            for rows in article_rows(session):
                vectors_by_id = vectors.article_vectors([row.id for row in rows])
                for row in rows:
                    fact = row.neutral_fact or {}
                    vector = vectors_by_id.get(row.id)
                    if not fact.get("fact") or not vector:
                        skipped += 1
                        continue
                    clusterer.process(ReplayArticle(
                        id=row.id,
                        source_id=row.source_id,
                        country=row.name,
                        fact=fact,
                        vector=vector,
                        observed_at=row.observed_at,
                    ))
                session.flush()
            summary = clusterer.finalize()
            summary["skipped_missing_fact_vector"] = skipped
            run.status = "succeeded"
            run.completed_at = datetime.now(timezone.utc)
            session.commit()
        except Exception:
            session.rollback()
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            session.commit()
            raise
        output = report(session, clusterer, summary)
        labels = export_labels(session, run.id)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    labels_path.write_text(json.dumps(labels, indent=2, ensure_ascii=False), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    args = parser.parse_args()
    print(json.dumps(run(args.database_url, args.reset, args.report, args.labels), indent=2))


if __name__ == "__main__":
    main()
