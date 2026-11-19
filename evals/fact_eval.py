import argparse
import itertools
import json
from dataclasses import dataclass
from pathlib import Path

import numpy
from requests import RequestException
from sqlalchemy import select

from cron.ai.service import AIService
from cron.util.article import get_article_content
from shared.database import SessionLocal
from shared.models import Articles
from shared.search_service import SearchService


EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_LABELS = EVAL_DIR / "golden" / "fact_pairs.json"
DEFAULT_RESULTS = EVAL_DIR / "results" / "fact_eval.json"


@dataclass
class EvalArticle:
    id: int
    headline: str
    link: str
    embedding: list[float]


def cosine(left: list[float], right: list[float]) -> float:
    left_array = numpy.array(left, dtype=numpy.float32)
    right_array = numpy.array(right, dtype=numpy.float32)
    return float(left_array @ right_array / (
        numpy.linalg.norm(left_array) * numpy.linalg.norm(right_array)
    ))


def load_labels(path: Path) -> list[dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    events = document.get("events")
    negatives = document.get("different_event_pairs")
    if not isinstance(events, list) or not events:
        raise ValueError("labels require a non-empty events list")
    if not isinstance(negatives, list) or not negatives:
        raise ValueError("labels require different_event_pairs")
    pairs = []
    for event in events:
        ids = event.get("article_ids")
        if not isinstance(ids, list) or len(ids) < 2:
            raise ValueError("every event needs at least two article_ids")
        for left_id, right_id in itertools.combinations(ids, 2):
            pairs.append({
                "left_id": left_id,
                "right_id": right_id,
                "same_event": True,
                "event": event.get("name", ""),
            })
    for pair in negatives:
        if not isinstance(pair, dict):
            raise ValueError("different_event_pairs entries must be objects")
        pairs.append({**pair, "same_event": False})
    for pair in pairs:
        if not all(key in pair for key in ("left_id", "right_id", "same_event")):
            raise ValueError("every pair needs left_id, right_id, same_event")
        if not isinstance(pair["same_event"], bool):
            raise ValueError("same_event must be boolean")
    return pairs


def articles_for(ids: set[int]) -> dict[int, EvalArticle]:
    with SessionLocal() as session:
        rows = session.execute(
            select(
                Articles.id,
                Articles.headline,
                Articles.link,
                Articles.embedding,
            ).where(Articles.id.in_(ids))
        ).all()
    return {
        row.id: EvalArticle(
            id=row.id,
            headline=row.headline,
            link=row.link,
            embedding=row.embedding,
        )
        for row in rows
    }


def fact_for(article: EvalArticle, service: AIService) -> str:
    try:
        content = get_article_content(article.link)
    except RequestException as error:
        raise ValueError(
            f"article {article.id} could not be fetched: {error}"
        ) from error
    if content == "empty article.":
        raise ValueError(f"article {article.id} has no extractable content")
    parsed = service.summarize(article.headline, content)
    if not parsed:
        raise ValueError(f"article {article.id} could not be summarized")
    return parsed.neutral_fact.fact


def best_threshold(scores: list[tuple[float, bool]]) -> dict:
    thresholds = sorted({score for score, _ in scores})
    best = {"f1": -1.0}
    for threshold in thresholds:
        tp = sum(score >= threshold and label for score, label in scores)
        fp = sum(score >= threshold and not label for score, label in scores)
        fn = sum(score < threshold and label for score, label in scores)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        if f1 > best["f1"]:
            best = {"threshold": threshold, "precision": precision, "recall": recall, "f1": f1}
    return best


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS)
    args = parser.parse_args()
    pairs = load_labels(args.labels)
    articles = articles_for({pair[key] for pair in pairs for key in ("left_id", "right_id")})
    missing = sorted({pair[key] for pair in pairs for key in ("left_id", "right_id")} - articles.keys())
    if missing:
        raise ValueError(f"unknown article ids: {missing}")

    ai_service = AIService()
    search_service = SearchService()
    facts = {}
    skipped_articles = {}
    for article_id, article in articles.items():
        try:
            facts[article_id] = fact_for(article, ai_service)
        except ValueError as error:
            skipped_articles[article_id] = str(error)

    pairs = [
        pair for pair in pairs
        if pair["left_id"] in facts and pair["right_id"] in facts
    ]
    if not pairs:
        raise ValueError("no labelled pairs had extractable article content")

    vectors = {article_id: search_service.embed(fact) for article_id, fact in facts.items()}
    results = []
    for pair in pairs:
        left = articles[pair["left_id"]]
        right = articles[pair["right_id"]]
        results.append({
            **pair,
            "left_fact": facts[left.id],
            "right_fact": facts[right.id],
            "fact_similarity": cosine(vectors[left.id], vectors[right.id]),
            "dense_similarity": cosine(left.embedding, right.embedding),
        })

    fact_scores = [(row["fact_similarity"], row["same_event"]) for row in results]
    dense_scores = [(row["dense_similarity"], row["same_event"]) for row in results]
    output = {
        "pairs": results,
        "facts": facts,
        "skipped_articles": skipped_articles,
        "fact": {"best_f1": best_threshold(fact_scores)},
        "dense": {"best_f1": best_threshold(dense_scores)},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
