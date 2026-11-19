from sqlalchemy import select
from requests import RequestException

from cron.ai.service import AIService
from cron.util.article import get_article_content
from cron.util.backfill_vectors import (
    FACT_VECTOR,
    create_collection,
    get_client,
    upsert_article,
)
from cron.util.log import add_log
from shared.database import SessionLocal
from shared.models import Articles
from shared.search_service import COLLECTION, SearchService
from qdrant_client import models


BATCH_SIZE = 25


def backfill_facts() -> int:
    ai_service = AIService()
    search_service = SearchService()
    client = get_client()
    create_collection(client)
    completed = 0

    with SessionLocal() as session:
        statement = select(Articles).order_by(Articles.id)
        articles = session.execute(statement).scalars().yield_per(BATCH_SIZE)
        for article in articles:
            fact = (article.neutral_fact or {}).get("fact")
            if not fact:
                try:
                    content = get_article_content(article.link)
                except RequestException as exception:
                    add_log(
                        f"fact backfill article {article.id}: fetch failed "
                        f"({type(exception).__name__}): {exception}"
                    )
                    continue
                if content == "empty article.":
                    continue
                try:
                    parsed = ai_service.summarize(article.headline, content)
                except Exception as exception:
                    add_log(
                        f"fact backfill article {article.id}: summarization failed "
                        f"({type(exception).__name__}): {exception}"
                    )
                    continue
                if not parsed:
                    continue
                article.neutral_fact = parsed.neutral_fact.model_dump()
                session.commit()
                fact = article.neutral_fact["fact"]

            try:
                record = client.retrieve(
                    COLLECTION,
                    [article.id],
                    with_payload=False,
                    with_vectors=[FACT_VECTOR],
                )
                if record and FACT_VECTOR in (record[0].vector or {}):
                    continue
                if not record:
                    upsert_article(article, search_service)
                else:
                    client.update_vectors(
                        COLLECTION,
                        [models.PointVectors(id=article.id, vector={
                            FACT_VECTOR: search_service.embed(fact),
                        })],
                        wait=True,
                    )
            except Exception as exception:
                add_log(
                    f"fact backfill article {article.id}: Qdrant update failed "
                    f"({type(exception).__name__}): {exception}"
                )
                continue
            completed += 1
            print(f"backfilled {completed}: article {article.id}")

    return completed


if __name__ == "__main__":
    print(f"backfilled {backfill_facts()} facts")
