
from sqlalchemy import (
    select
)

from shared.search_service import SearchService
from shared.database import SessionLocal
from shared.models import (
    Articles
)


def backfill() -> None:
    search_service = SearchService()

    # grab articles that aren't embedded
    with SessionLocal() as session:
        statement = (
            select(Articles)
            .where(Articles.embedding.is_(None))
        )
        unembedded_articles = session.execute(statement).scalars().all()

        # iterate through unembedded articles
        for article in unembedded_articles:

            # embed each unembedded article
            text_to_embed = article.embedding_text()
            embedding = search_service.embed(text_to_embed)
            article.embedding = embedding
            session.add(article)
            session.commit()


if __name__ == "__main__":
    backfill()