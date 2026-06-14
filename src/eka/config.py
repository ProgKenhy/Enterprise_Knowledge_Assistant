from functools import lru_cache
from pathlib import Path

from pydantic import RedisDsn, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """App settings"""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )

    # App
    APP_NAME: str = "Enterprise RAG"
    DEBUG: bool = False
    SECRET_KEY: str = "my_secret_key_change_it_on_production!"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_PORT_FORWARD: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: SecretStr = SecretStr("postgres")
    POSTGRES_DB: str = "eka"

    @property
    def db_port(self) -> int:
        if self.POSTGRES_HOST == "localhost":
            return self.POSTGRES_PORT_FORWARD
        return self.POSTGRES_PORT

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PORT_FORWARD: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: SecretStr | None = None

    @property
    def redis_port(self) -> int:
        if self.REDIS_HOST == "localhost":
            return self.REDIS_PORT_FORWARD
        return self.REDIS_PORT

    # Qdrant
    QDRANT_URL: str = "http://qdrant:6333"
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION: str = "knowledge_base"

    # Embeddings
    EMBEDDING_SPARSE_MODEL: str = "Qdrant/bm25"
    EMBEDDING_DENSE_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDING_PROVIDER: str = "local"
    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str | None = None
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_DIM: int = 384

    # Reranker
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKER_TOP_K: int = 5

    # LLM
    LLM_PROVIDER: str = "ollama"  # openai, anthropic, ollama
    LLM_MODEL: str = "qwen2.5:7b"
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_TOKENS: int = 1500

    # Documents
    UPLOAD_DIR: Path = Path(BASE_DIR / "uploads")

    # RAG
    RETRIEVAL_TOP_K: int = 20  # Сколько кандидатов для reranker
    RERANK_TOP_K: int = 7  # Сколько после reranking
    CHUNK_SIZE: int = 512  # Токены
    CHUNK_OVERLAP: int = 50  # Токены

    # Cache
    CACHE_TTL: int = 3600  # Секунды
    SEMANTIC_CACHE_THRESHOLD: float = 0.95

    # Celery
    CELERY_BROKER_URL: str = "amqp://guest:guest@rabbitmq:5672//"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Auth
    JWT_ALG: str = "RS256"
    JWT_PRIVATE_KEY_PATH: Path = Path(BASE_DIR / "keys/private.pem")
    JWT_PUBLIC_KEY_PATH: Path = Path(BASE_DIR / "keys/public.pem")
    ACCESS_TOKEN_EXPIRE_SECONDS: int = 15 * 60
    REFRESH_TOKEN_EXPIRE_SECONDS: int = 7 * 24 * 60 * 60  # 7 дней

    @property
    def postgres_async_url(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD.get_secret_value()}@{self.POSTGRES_HOST}:{self.db_port}/{self.POSTGRES_DB}"

    @property
    def postgres_sync_url(self) -> str:
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD.get_secret_value()}@{self.POSTGRES_HOST}:{self.db_port}/{self.POSTGRES_DB}"

    @computed_field
    @property
    def redis_url(self) -> str:
        redis_dsn = RedisDsn.build(
            scheme="redis",
            username=None,
            password=(self.REDIS_PASSWORD.get_secret_value() if self.REDIS_PASSWORD else None),
            host=self.REDIS_HOST,
            port=self.REDIS_PORT,
            path=f"{self.REDIS_DB}",
        )
        return str(redis_dsn)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
