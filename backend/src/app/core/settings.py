from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """
    Settings for LLM.
    - url: Base URL of LiteLLM (e.g. http://localhost:4000). We expose openai_base_url with /v1 for ChatOpenAI.
    - number_of_messages_to_contextualize: Number of messages to contextualize.
    - message_token_threshold: Message token threshold for summarization.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        env_prefix="",
    )

    litellm_url: str = "http://localhost:4000"
    number_of_messages_to_contextualize: int = 6
    message_token_threshold: int = 10

    # Model configurations
    primary_model: str = "primary-llm"
    secondary_model: str = "secondary-llm"
    primary_temperature: float = 0.7
    secondary_temperature: float = 0.0
    max_retries: int = 2

    @property
    def openai_base_url(self) -> str:
        """URL for OpenAI client: base + /v1 (LiteLLM serves at /v1/chat/completions)."""
        base = self.litellm_url.rstrip("/")
        return f"{base}/v1" if not base.endswith("/v1") else base


class QdrantSettings(BaseSettings):
    """Settings for Qdrant vector database connection and model configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        env_prefix="QDRANT_",
    )

    host: str = "localhost"
    port: str = "6333"
    collection: str = "movies_collection"
    api_key: str | None = None

    dense_model_name: str = (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    sparse_model_name: str = "prithivida/Splade_PP_en_v1"
    reranker_model_name: str = "jinaai/jina-reranker-v2-base-multilingual"
    chunk_size: int = 512

    @property
    def qdrant_endpoint(self) -> str:
        return f"http://{self.host}:{self.port}"


class ApiSettings(BaseSettings):
    """API server and database connection settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    database_uri: str = (
        "postgresql+asyncpg://postgres:mysecretpassword@localhost:5432/chatdb"
    )

    @property
    def base_url(self) -> str:
        """Return the base URL of the API server."""
        return f"http://{self.host}:{self.port}"


class RedisSettings(BaseSettings):
    """Redis connection and stream-bus settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        env_prefix="REDIS_",
    )

    url: str = "redis://localhost:6379/0"
    stream_key_prefix: str = "stream:chat:"
    stream_ttl: int = 3600
    active_generation_ttl: int = 3600
    interrupt_ttl: int = 3600
    stream_read_block_ms: int = 500


class LoggingSettings(BaseSettings):
    """Global logging/environment settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    environment: str = "development"
    log_level: str = "info"
    log_format: str = "text"  # "text" | "json"


class ObservabilitySettings(BaseSettings):
    """Langfuse observability settings. Empty keys => disabled."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        env_prefix="LANGFUSE_",
    )

    host: str = ""
    public_key: str = ""
    secret_key: str = ""
    sample_rate: float = 1.0

    @property
    def enabled(self) -> bool:
        return bool(self.public_key and self.secret_key)


api_settings = ApiSettings()
qdrant_settings = QdrantSettings()
llm_settings = LLMSettings()
redis_settings = RedisSettings()
logging_settings = LoggingSettings()
observability_settings = ObservabilitySettings()
