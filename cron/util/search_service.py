
from openai import OpenAI
from sqlalchemy import (
    select,
    func
)

from shared.database import SessionLocal
from shared.models import Articles

RRF_K = 60


class SearchService:
    def __init__(self, model: str = "text-embedding-3-small"):
        self.client = OpenAI()
        self.model = model

    def _deduplicate(self, articles: list[tuple[Articles, float]]) -> list[
                    tuple[Articles, float]]:
        """
        Removes duplicate articles while preserving their original ranking.
        The first occurrence of each article link is retained.

        :param articles: the ordered articles and their relevance scores
        :return: the ordered articles with duplicate links removed
        """

        deduplicated_articles = {}
        for article, score in articles:
            if article.link in deduplicated_articles:
                continue
            deduplicated_articles[article.link] = (article, score)

        return list(deduplicated_articles.values())


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

    def lexical_search(self, text: str) -> list[tuple[Articles, float]]:
        """
        Searches for articles that contain terms from the provided text.
        Results are ordered from most to least lexically relevant using
        cover-density ranking.

        :param text: the search query to compare against article text
        :return: up to 50 matching articles and their lexical relevance scores
        """

        article_text = func.concat(
            Articles.translated_headline,
            " ",
            Articles.summary
        )

        search_vector = func.to_tsvector("english", article_text)
        search_query = func.websearch_to_tsquery("english", text)
        search_result = None

        with SessionLocal() as session:
            score = func.ts_rank_cd(search_vector, search_query)
            statement = (
                select(Articles, score.label("rank"))
                .where(search_vector.op("@@")(search_query))
                .order_by(score.desc())
                .limit(50)
            )
            search_result = session.execute(statement).all()

        return self._deduplicate(search_result)


    def semantic_search(self, text: str) -> list[tuple[Articles, float]]:
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
        search_result = None

        with SessionLocal() as session:
            statement = (
                select(Articles, distance.label("distance"))
                .where(Articles.embedding.is_not(None))
                .order_by(distance)
                .limit(50)
            )

            search_result = session.execute(statement).all()

        return self._deduplicate(search_result)

    def hybrid_search(self, text: str) -> list[tuple[int, Articles]]:
        """
        Combines lexical and semantic search results using reciprocal rank
        fusion. Results appearing highly in either search receive a combined
        score and are ordered from most to least relevant.

        :param text: the query to search for across stored articles
        :return: the ranked result positions and their corresponding articles
        """

        lexical_search = self.lexical_search(text)
        semantic_search = self.semantic_search(text)

        scores = {}

        for i, (article, score) in enumerate(lexical_search):
            if article.link in scores:
                continue
            scores[article.link] = {}
            scores[article.link]["score"] = (1 / (RRF_K + (i + 1)))
            scores[article.link]["article"] = article

        for i, (article, score) in enumerate(semantic_search):
            if article.link in scores:
                scores[article.link]["score"] += (1 / (RRF_K + (i + 1)))
            else:
                scores[article.link] = {}
                scores[article.link]["score"] = (1 / (RRF_K + (i + 1)))
                scores[article.link]["article"] = article

        sorted_scores = dict(sorted(scores.items(), key=lambda item: item[1][
                                    "score"], reverse=True))

        search_result = [(i + 1, article_object["article"]) for i,
                         article_object in enumerate(sorted_scores.values())]
        return search_result[:15]

if __name__ == "__main__":
    service = SearchService()
    hybrid_search = service.hybrid_search("iran bombs kuwait")
