
from collections.abc import Sequence

from openai import OpenAI
from sqlalchemy import (
    select,
    func
)
from sqlalchemy.engine import Row

from shared.database import SessionLocal
from shared.models import Articles

class SearchService:
    def __init__(self, model: str = "text-embedding-3-small"):
        self.client = OpenAI()
        self.model = model

    def embed(self, text: str) -> list[float]:
        """
        Embeds an article text into an embedding vector.
        The text will be in this format:
        <headline>:<summary>

        :param text: the text to embed
        :return: a list of floats to represent embedding vector
        """

        response = self.client.embeddings.create(
            input=text,
            model=self.model,
        )

        return response.data[0].embedding

    def lexical_search(self, text: str) -> list[float]:
        """


        :param text:
        :return:
        """

        article_text = func.concat(
            Articles.translated_headline,
            " ",
            Articles.summary
        )

        search_vector = func.to_tsvector("english", article_text)
        search_query = func.websearch_to_tsquery("english", text)
        rank = func.ts_rank_cd(search_vector, search_query)

        statement = (
            select(Articles, rank.label("rank"))
            .where(search_vector.op("@@")(search_query))
            .order_by(rank.desc())
            .limit(50)
        )

        with SessionLocal() as session:
            return session.execute(statement).all()

    def semantic_search(self, text: str) -> Sequence[Row[tuple[Articles,
                                                     float]]]:
        """
        Searches for articles that are semantically similar to the provided
        text. The query is embedded and compared against stored article
        embeddings using cosine distance. Results are ordered from most to
        least similar.

        :param text: the query to compare against article embeddings
        :return: the 50 closest articles and their cosine distances
        """

        query_vector = self.embed(text)
        distance = Articles.embedding.cosine_distance(query_vector)

        with SessionLocal() as session:
            statement = (
                select(Articles, distance.label("distance"))
                .where(Articles.embedding.is_not(None))
                .order_by(distance)
                .limit(50)
            )

            return session.execute(statement).all()
