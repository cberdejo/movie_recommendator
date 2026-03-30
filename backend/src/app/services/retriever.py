import tqdm
from fastembed.rerank.cross_encoder import TextCrossEncoder
from langchain_core.documents import Document
from qdrant_client import AsyncQdrantClient, models

from app.core.config.settings import qdrantsettings


class HybridSearcher:
    dense_vector_name = "dense"
    sparse_vector_name = "sparse"
    dense_model_name = qdrantsettings.dense_model_name
    sparse_model_name = qdrantsettings.sparse_model_name
    reranker_model_name = qdrantsettings.reranker_model_name

    def __init__(self, url: str, collection_name: str):
        self.collection_name = collection_name
        self.async_qdrant_client = AsyncQdrantClient(url=url)
        self.reranker = TextCrossEncoder(model_name=self.reranker_model_name)

    async def create_collection(self, recreate: bool = False):
        """
        Create the Qdrant collection with hybrid vector configuration.
        If recreate is True, the collection will be deleted if it exists.
        """
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
                },  # size and distance are model dependent
                sparse_vectors_config={
                    self.sparse_vector_name: models.SparseVectorParams()
                },
            )

    async def index(self, chunks: list[Document], verbose: bool = False):
        """Index documents into the Qdrant collection."""
        vectors = []
        payload = []
        for chunk in chunks:
            dense_document = models.Document(
                text=chunk.page_content, model=self.dense_model_name
            )
            sparse_document = models.Document(
                text=chunk.page_content, model=self.sparse_model_name
            )
            vectors.append(
                {
                    self.dense_vector_name: dense_document,
                    self.sparse_vector_name: sparse_document,
                }
            )
            payload.append(
                {
                    "metadata": chunk.metadata,
                    "page-content": chunk.page_content,
                }
            )
        self.async_qdrant_client.upload_collection(
            collection_name=self.collection_name,
            vectors=tqdm.tqdm(vectors) if verbose else vectors,
            payload=payload,
        )

    async def search(self, text: str, rerank: bool = False) -> list[dict]:
        """Perform a hybrid search with optional re-ranking."""
        search_result = await self.async_qdrant_client.query_points(
            collection_name=self.collection_name,
            query=models.FusionQuery(
                fusion=models.Fusion.RRF,
            ),
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
            query_filter=None,
            limit=15 if rerank else 5,
        )
        if rerank:
            # Re-ranking results to select top K most relevant documents.
            new_scores = list(
                self.reranker.rerank(
                    text, [hit.payload["page-content"] for hit in search_result.points]
                )
            )

            ranking = [(i, score) for i, score in enumerate(new_scores)]
            ranking.sort(
                key=lambda x: x[1], reverse=True
            )  # sorting them in order of relevance defined by reranker

            reranked_points = [search_result.points[i] for i, _ in ranking]
            chunks = [
                point.payload for point in reranked_points[:5]
            ]  # return top 5 results
        else:
            chunks = [point.payload for point in search_result.points]
        return chunks


class SemanticSearcher:
    dense_vector_name = "dense"
    dense_model_name = qdrantsettings.dense_model_name
    semantic_reranker_model_name = qdrantsettings.semantic_reranker_model_name

    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        self.async_qdrant_client = AsyncQdrantClient(url=qdrantsettings.qdrant_endpoint)
        self.semantic_reranker = TextCrossEncoder(
            model_name=self.semantic_reranker_model_name
        )

    async def create_collection(self):
        """Create the Qdrant collection with hybrid vector configuration."""
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
                },  # size and distance are model dependent
            )

    async def index(self, chunks: list[Document]):
        """Index documents into the Qdrant collection."""
        vectors = []
        payload = []
        for chunk in chunks:
            dense_document = models.Document(
                text=chunk.page_content, model=self.dense_model_name
            )
            vectors.append(
                {
                    self.dense_vector_name: dense_document,
                }
            )
            payload.append(
                {
                    "metadata": chunk.metadata,
                    "page-content": chunk.page_content,
                }
            )
        self.async_qdrant_client.upload_collection(
            collection_name=self.collection_name,
            vectors=tqdm.tqdm(vectors),
            payload=payload,
        )

    async def search(self, text: str, rerank: bool = False) -> list[dict]:
        """Perform a semantic search with optional re-ranking."""
        search_result = await self.async_qdrant_client.query_points(
            collection_name=self.collection_name,
            query=models.FusionQuery(
                fusion=models.Fusion.RRF,
            ),
            prefetch=[
                models.Prefetch(
                    query=models.Document(text=text, model=self.dense_model_name),
                    using=self.dense_vector_name,
                )
            ],
            query_filter=None,
            limit=15 if rerank else 5,
        )
        if rerank:
            # Re-ranking results to select top K most relevant documents.
            new_scores = list(
                self.semantic_reranker.rerank(
                    text, [hit.payload["page-content"] for hit in search_result.points]
                )
            )

            ranking = [(i, score) for i, score in enumerate(new_scores)]
            ranking.sort(
                key=lambda x: x[1], reverse=True
            )  # sorting them in order of relevance defined by reranker

            reranked_points = [search_result.points[i] for i, _ in ranking]
            chunks = [
                point.payload for point in reranked_points[:5]
            ]  # return top 5 results
        else:
            chunks = [point.payload for point in search_result.points]
        return chunks
