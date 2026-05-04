import os
from pydantic_settings import BaseSettings


class LLMSettings(BaseSettings):
    """
    Settings for LLM.
    - url: Base URL of LiteLLM (e.g. http://localhost:4000). We expose openai_base_url with /v1 for ChatOpenAI.
    - number_of_messages_to_contextualize: Number of messages to contextualize.
    - message_token_threshold: Message token threshold for summarization.
    """

    url: str = os.getenv("LITELLM_URL", "http://localhost:4000")
    number_of_messages_to_contextualize: int = os.getenv(
        "NUMBER_OF_MESSAGES_TO_CONTEXTUALIZE", 6
    )
    message_token_threshold: int = os.getenv("MESSAGE_TOKEN_THRESHOLD", 10)

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
    qdrant_host: str = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port: str = os.getenv("QDRANT_PORT", "6333")
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "movies_collection")
    qdrant_api_key: str | None = os.getenv("QDRANT_API_KEY")

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
    chunk_size: int = os.getenv("CHUNK_SIZE", 512)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"

    @property
    def qdrant_endpoint(self) -> str:
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


class RedisSettings(BaseSettings):
    """Redis connection and stream-bus settings."""

    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    stream_key_prefix: str = os.getenv("STREAM_KEY_PREFIX", "stream:chat:")
    stream_ttl: int = int(os.getenv("STREAM_TTL", "3600"))
    active_generation_ttl: int = int(os.getenv("ACTIVE_GENERATION_TTL", "3600"))
    interrupt_ttl: int = int(os.getenv("INTERRUPT_TTL", "3600"))
    stream_read_block_ms: int = int(os.getenv("STREAM_READ_BLOCK_MS", "500"))

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"


class LoggingSettings(BaseSettings):
    """Global logging/environment settings."""

    environment: str = os.getenv("ENVIRONMENT", "development")
    log_level: str = os.getenv("LOG_LEVEL", "info")
    log_format: str = os.getenv("LOG_FORMAT", "text")  # "text" | "json"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"


class ObservabilitySettings(BaseSettings):
    """Langfuse observability settings. Empty keys => disabled."""

    langfuse_host: str = os.getenv("LANGFUSE_HOST", "")
    langfuse_public_key: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    langfuse_secret_key: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    langfuse_sample_rate: float = float(os.getenv("LANGFUSE_SAMPLE_RATE", "1.0"))

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"

    @property
    def enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


apisettings = ApiSettings()
qdrantsettings = QdrantSettings()
llmsettings = LLMSettings()
redissettings = RedisSettings()
loggingsettings = LoggingSettings()
observabilitysettings = ObservabilitySettings()
