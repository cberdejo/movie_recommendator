import math
import uuid

import tqdm
from fastembed.rerank.cross_encoder import TextCrossEncoder
from langchain_core.documents import Document
from qdrant_client import AsyncQdrantClient, models

from app.core.settings import qdrantsettings


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class HybridSearcher:
    dense_vector_name = "dense"
    sparse_vector_name = "sparse"
    dense_model_name = qdrantsettings.dense_model_name
    sparse_model_name = qdrantsettings.sparse_model_name
    reranker_model_name = qdrantsettings.reranker_model_name

    def __init__(
        self,
        url: str,
        collection_name: str,
        prefetch_limit: int = 15,
        final_limit: int = 5,
    ):
        self.collection_name = collection_name
        self.async_qdrant_client = AsyncQdrantClient(url=url)
        self.reranker = TextCrossEncoder(model_name=self.reranker_model_name)
        self.prefetch_limit = prefetch_limit
        self.final_limit = final_limit

    async def create_collection(self, recreate: bool = False) -> None:
        if recreate and await self.async_qdrant_client.collection_exists(
            self.collection_name
        ):
            await self.async_qdrant_client.delete_collection(self.collection_name)

        if not await self.async_qdrant_client.collection_exists(self.collection_name):
            await self.async_qdrant_client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    self.dense_vector_name: models.VectorParams(
                        size=self.async_qdrant_client.get_embedding_size(
                            self.dense_model_name
                        ),
                        distance=models.Distance.COSINE,
                    )
                },
                sparse_vectors_config={
                    self.sparse_vector_name: models.SparseVectorParams()
                },
            )

    async def index(self, chunks: list[Document], verbose: bool = False) -> None:
        """Index documents into the Qdrant collection in async batches."""
        points = [
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector={
                    self.dense_vector_name: models.Document(
                        text=chunk.page_content, model=self.dense_model_name
                    ),
                    self.sparse_vector_name: models.Document(
                        text=chunk.page_content, model=self.sparse_model_name
                    ),
                },
                payload={
                    "metadata": chunk.metadata,
                    "page-content": chunk.page_content,
                },
            )
            for chunk in chunks
        ]

        batch_size = 64
        iterator = range(0, len(points), batch_size)
        if verbose:
            iterator = tqdm.tqdm(iterator, desc="Indexing")

        for i in iterator:
            await self.async_qdrant_client.upsert(
                collection_name=self.collection_name,
                points=points[i : i + batch_size],
            )

    async def search(
        self,
        text: str,
        rerank: bool = True,
        filter: models.Filter | None = None,
        prefetch_limit: int | None = None,
        final_limit: int | None = None,
    ) -> list[dict]:
        """Hybrid search (dense + sparse RRF) with optional cross-encoder reranking.

        Scores returned:
          - rerank=True:  sigmoid-normalised cross-encoder score in [0, 1]
          - rerank=False: raw RRF score from Qdrant
        """
        prefetch_limit = prefetch_limit or self.prefetch_limit
        final_limit = final_limit or self.final_limit

        result = await self.async_qdrant_client.query_points(
            collection_name=self.collection_name,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            prefetch=[
                models.Prefetch(
                    query=models.Document(text=text, model=self.dense_model_name),
                    using=self.dense_vector_name,
                ),
                models.Prefetch(
                    query=models.Document(text=text, model=self.sparse_model_name),
                    using=self.sparse_vector_name,
                ),
            ],
            query_filter=filter,
            limit=prefetch_limit,
        )

        points = result.points
        if not points:
            return []

        if rerank:
            texts = [p.payload["page-content"] for p in points]
            raw_scores = list(self.reranker.rerank(text, texts))
            norm_scores = [_sigmoid(s) for s in raw_scores]

            ranking = sorted(enumerate(norm_scores), key=lambda x: x[1], reverse=True)

            return [
                {
                    **points[i].payload,
                    "score": score,
                    "qdrant_score": float(points[i].score)
                    if points[i].score is not None
                    else None,
                }
                for i, score in ranking[:final_limit]
            ]

        return [
            {
                **p.payload,
                "score": float(p.score) if p.score is not None else None,
            }
            for p in points[:final_limit]
        ]
