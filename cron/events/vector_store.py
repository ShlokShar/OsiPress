from datetime import datetime, timedelta

import numpy
from qdrant_client import QdrantClient, models

from cron.events.config import TOP_K, WINDOW_DAYS
from cron.util.backfill_vectors import EMBEDDING_SIZE, get_client
from shared.search_service import COLLECTION


class EventVectorStore:
    def __init__(self, collection: str):
        self.client: QdrantClient = get_client()
        self.collection = collection

    def reset(self) -> None:
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            self.collection,
            vectors_config={
                "centroid": models.VectorParams(
                    size=EMBEDDING_SIZE,
                    distance=models.Distance.COSINE,
                ),
                "anchor": models.VectorParams(
                    size=EMBEDDING_SIZE,
                    distance=models.Distance.COSINE,
                ),
            },
        )
        self.client.create_payload_index(
            self.collection,
            "last_seen",
            models.PayloadSchemaType.DATETIME,
        )

    def candidates(
        self,
        vector: list[float],
        observed_at: datetime,
    ) -> list[models.ScoredPoint]:
        since = observed_at - timedelta(days=WINDOW_DAYS)
        return self.client.query_points(
            self.collection,
            query=vector,
            using="centroid",
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="last_seen",
                        range=models.DatetimeRange(gte=since),
                    ),
                ],
            ),
            limit=TOP_K,
            with_payload=True,
            with_vectors=["centroid", "anchor"],
        ).points

    def upsert(
        self,
        event_id: int,
        centroid: list[float],
        anchor: list[float],
        status: str,
        last_seen: datetime,
    ) -> None:
        self.client.upsert(
            self.collection,
            points=[
                models.PointStruct(
                    id=event_id,
                    vector={"centroid": centroid, "anchor": anchor},
                    payload={"status": status, "last_seen": last_seen},
                ),
            ],
            wait=True,
        )

    def article_vectors(self, article_ids: list[int]) -> dict[int, list[float]]:
        points = self.client.retrieve(
            COLLECTION,
            article_ids,
            with_payload=False,
            with_vectors=["fact"],
        )
        return {
            int(point.id): point.vector["fact"]
            for point in points
            if isinstance(point.vector, dict) and "fact" in point.vector
        }

    def delete(self, event_ids: list[int]) -> None:
        if event_ids:
            self.client.delete(
                self.collection,
                points_selector=models.PointIdsList(points=event_ids),
                wait=True,
            )

    def set_status(self, event_ids: list[int], status: str) -> None:
        if event_ids:
            self.client.set_payload(
                self.collection,
                payload={"status": status},
                points=event_ids,
                wait=True,
            )

    @staticmethod
    def centroid(vectors: list[list[float]]) -> list[float]:
        values = numpy.array(vectors, dtype=numpy.float32)
        mean = values.mean(axis=0)
        norm = numpy.linalg.norm(mean)
        return (mean / norm).tolist() if norm else mean.tolist()
