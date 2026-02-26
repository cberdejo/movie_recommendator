import os
from enum import Enum
from pydantic_settings import BaseSettings

class LiteLLMSettings(BaseSettings):
    # Base URL of LiteLLM (e.g. http://localhost:4000). We expose openai_base_url with /v1 for ChatOpenAI.
    url: str = os.getenv("LITELLM_URL", "http://localhost:4000")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"

    @property
    def openai_base_url(self) -> str:
        """URL for OpenAI client: base + /v1 (LiteLLM serves at /v1/chat/completions)."""
        base = self.url.rstrip("/")
        return f"{base}/v1" if not base.endswith("/v1") else base

class QdrantSettings(BaseSettings):
    # Core connection settings
    qdrant_host: str = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port: str = os.getenv("QDRANT_PORT", "6333")
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "movies_collection")
    qdrant_api_key: str | None = os.getenv("QDRANT_API_KEY")

    # Model names used across the app (retrieval + ingest)
    dense_model_name: str = os.getenv(
        "DENSE_MODEL_NAME",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    sparse_model_name: str = os.getenv(
        "SPARSE_MODEL_NAME",
        "prithivida/Splade_PP_en_v1",
    )
    reranker_model_name: str = os.getenv(
        "RERANKER_MODEL_NAME", "jinaai/jina-reranker-v2-base-multilingual"
    )
    semantic_reranker_model_name: str = os.getenv(
        "SEMANTIC_RERANKER_MODEL_NAME", "BAAI/bge-reranker-base"
    )
    chunk_size: int = os.getenv("CHUNK_SIZE", 512)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"

    @property
    def qdrant_endpoint(self) -> str:
        """HTTP endpoint for Qdrant."""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"


class ApiSettings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    database_uri: str = (
        "postgresql+asyncpg://postgres:mysecretpassword@localhost:5432/chatdb"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"

    @property
    def get_uri(self) -> str:
        return f"http://{self.host}:{self.port}"


apisettings = ApiSettings()
qdrantsettings = QdrantSettings()
llmsettings = LiteLLMSettings()