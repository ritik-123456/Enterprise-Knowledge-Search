import os
import sys
from typing import Optional
from pydantic import Field, SecretStr, AliasChoices, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_ENV_PATH = os.path.join(_BACKEND_DIR, ".env")


class Settings(BaseSettings):
    """
    Application Settings loaded from environment variables or .env file.
    OPENAI_API_KEY never lives in code and is loaded securely at runtime.
    """
    model_config = SettingsConfigDict(
        env_file=(_ENV_PATH, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )

    # Core Application Info
    PROJECT_NAME: str = "Enterprise Knowledge Search"
    API_PREFIX: str = "/api"

    # LLM & Embedding Credentials & Models
    # Loaded from env var or .env; default is empty string so secrets never live in source code.
    OPENAI_API_KEY: str = Field(
        default="",
        description="OpenAI API Key loaded securely from environment or .env"
    )
    GEMINI_API_KEY: str = Field(
        default="",
        description="Google Gemini API Key loaded securely from environment or .env"
    )
    OPENAI_BASE_URL: Optional[str] = Field(
        default=None,
        description="Optional custom base URL for inference (e.g. Google Gemini or Azure)"
    )
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    LLM_MODEL: str = "gpt-4o-mini"

    # Google OAuth 2.0 Credentials
    GOOGLE_CLIENT_ID: Optional[str] = Field(
        default=None,
        description="Google OAuth 2.0 Client ID"
    )
    GOOGLE_CLIENT_SECRET: Optional[SecretStr] = Field(
        default=None,
        description="Google OAuth 2.0 Client Secret (strictly confidential)"
    )
    AUTH_SECRET_KEY: Optional[SecretStr] = Field(
        default=None,
        validation_alias=AliasChoices("AUTH_SECRET_KEY", "JWT_SECRET", "SECRET_KEY"),
        description="Confidential secret key used to sign and verify JWT authentication tokens"
    )

    # Supabase Cloud Database Credentials (Strictly confidential)
    SUPABASE_URL: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_URL", "SUPABASE_PROJECT_URL", "NEXT_PUBLIC_SUPABASE_URL", "VITE_SUPABASE_URL"),
        description="Supabase project URL"
    )
    SUPABASE_KEY: Optional[SecretStr] = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_KEY", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_API_KEY"),
        description="Supabase API key / service key (strictly confidential)"
    )


    # Qdrant Vector Database Settings
    QDRANT_URL: Optional[str] = Field(
        default=None,
        description="Qdrant connection URL (e.g. http://localhost:6333 or Qdrant Cloud URL)"
    )
    QDRANT_API_KEY: Optional[SecretStr] = Field(
        default=None,
        description="Qdrant Cloud API Key as SecretStr"
    )
    COLLECTION_NAME: str = Field(
        default="enterprise_knowledge",
        validation_alias=AliasChoices("COLLECTION_NAME", "QDRANT_COLLECTION"),
        description="Qdrant vector collection name"
    )
    QDRANT_PATH: str = Field(
        default="./qdrant_storage",
        validation_alias=AliasChoices("QDRANT_PATH", "QDRANT_STORAGE_PATH"),
        description="Local on-disk Qdrant storage path"
    )

    # Token-based Chunking Parameters
    CHUNK_SIZE_TOKENS: int = Field(
        default=400,
        description="Target chunk size in tokens (counted via tiktoken)"
    )
    CHUNK_OVERLAP_TOKENS: int = Field(
        default=60,
        description="Chunk overlap in tokens (approx 15% of chunk size)"
    )

    # Retrieval & Reranking Architecture (Breadth then Depth)
    RETRIEVE_K: int = Field(
        default=35,
        description="Initial broad vector retrieval pool size (first pass)"
    )
    TOP_K_CHUNKS: int = Field(
        default=8,
        description="Narrowed top relevant chunks passed to LLM context after reranking"
    )
    MIN_SIMILARITY: float = Field(
        default=0.0,
        description="Minimum cosine similarity cutoff threshold for relevance (0.0 allows hybrid BM25 and LLM gating)"
    )

    # Processing & Ingestion Limits
    MAX_UPLOAD_MB: int = Field(
        default=25,
        description="Maximum permitted PDF upload size in Megabytes"
    )
    MAX_PAGES: int = Field(
        default=150,
        description="Maximum number of pages permitted per uploaded PDF document"
    )
    EMBED_BATCH_SIZE: int = Field(
        default=64,
        description="Batch size for generating embeddings via OpenAI Batch API"
    )

    # Generation Limits & Factual Q&A Temperature
    LLM_MAX_TOKENS: int = Field(
        default=1024,
        description="Maximum tokens allocated for synthesized answer generation"
    )
    LLM_TEMPERATURE: float = Field(
        default=0.0,
        description="Deterministic sampling temperature (0.0 for strictly factual, grounded Q&A)"
    )

    # -------------------------------------------------------------
    # Cross-Question Pipeline Improvements & Feature Flags
    # -------------------------------------------------------------
    PIPELINE_VERSION: str = Field(
        default="v2",
        description="Active pipeline version: 'v1' (legacy baseline) or 'v2' (improved layout/parent-child/rerank)"
    )
    ENABLE_QUERY_DECOMPOSITION: bool = Field(
        default=True,
        description="Toggle LLM classification & query decomposition into sub-questions and multi-hop iteration"
    )
    ENABLE_HYBRID_BM25: bool = Field(
        default=True,
        description="Toggle corpus-wide BM25 keyword retrieval fused with dense vectors via RRF"
    )
    ENABLE_RERANKER: bool = Field(
        default=True,
        description="Toggle cross-encoder reranking over wide candidate set (30-50 down to top 8-12)"
    )
    ENABLE_PARENT_CHILD: bool = Field(
        default=True,
        description="Toggle small-to-big retrieval (embed small child chunks, provide parent section context)"
    )
    ENABLE_DIVERSITY_MMR: bool = Field(
        default=True,
        description="Toggle Maximal Marginal Relevance (MMR) for diversity after reranking"
    )
    ENABLE_MULTI_DOC_BALANCE: bool = Field(
        default=True,
        description="Toggle guaranteed minimum chunks per document for multi-doc/comparison queries"
    )
    ENABLE_LAYOUT_PARSER: bool = Field(
        default=True,
        description="Toggle layout-aware PDF parser (pymupdf4llm) preserving tables and structure"
    )

    # Configurable Sizing for Parent-Child & Reranking
    CHILD_CHUNK_SIZE_TOKENS: int = Field(
        default=150,
        description="Target child chunk size in tokens for high-precision embedding"
    )
    CHILD_CHUNK_OVERLAP_TOKENS: int = Field(
        default=30,
        description="Child chunk overlap in tokens"
    )
    PARENT_CHUNK_SIZE_TOKENS: int = Field(
        default=600,
        description="Target parent section size in tokens passed to LLM for full grounding"
    )
    RERANK_TOP_N: int = Field(
        default=10,
        description="Top N chunks retained after cross-encoder reranking (8-12)"
    )
    MULTI_DOC_MIN_PER_DOC: int = Field(
        default=2,
        description="Guaranteed minimum chunks per document for multi-document queries"
    )
    COHERE_API_KEY: Optional[str] = Field(
        default=None,
        description="Optional Cohere API key for Cohere Rerank API"
    )

    # Backward compatibility properties for existing modules
    @property
    def CHUNK_SIZE(self) -> int:
        return self.CHUNK_SIZE_TOKENS

    @property
    def CHUNK_OVERLAP(self) -> int:
        return self.CHUNK_OVERLAP_TOKENS

    @property
    def QDRANT_COLLECTION(self) -> str:
        return self.COLLECTION_NAME

    @property
    def QDRANT_STORAGE_PATH(self) -> str:
        return self.QDRANT_PATH

    @property
    def active_api_key(self) -> str:
        """Returns the active API key: strictly prefers GEMINI_API_KEY when configured."""
        if self.GEMINI_API_KEY and self.GEMINI_API_KEY.strip():
            return self.GEMINI_API_KEY.strip()
        return self.OPENAI_API_KEY.strip() if self.OPENAI_API_KEY else ""

    @property
    def is_gemini(self) -> bool:
        """Returns True if targeting Google Gemini API."""
        if self.LLM_MODEL.lower().startswith(("o1", "o3")):
            return False
        if bool(self.GEMINI_API_KEY and self.GEMINI_API_KEY.strip()):
            return True
        key = self.active_api_key
        return (
            "gemini" in self.LLM_MODEL.lower()
            or key.startswith("AQ.")
            or key.startswith("AIza")
            or (bool(self.OPENAI_BASE_URL) and "generativelanguage.googleapis.com" in str(self.OPENAI_BASE_URL))
        )

    @property
    def active_supabase_url(self) -> Optional[str]:
        """Returns the configured Supabase URL if present."""
        if self.SUPABASE_URL and self.SUPABASE_URL.strip():
            return self.SUPABASE_URL.strip()
        return os.getenv("SUPABASE_URL") or os.getenv("SUPABASE_PROJECT_URL")

    @property
    def active_supabase_key(self) -> Optional[str]:
        """Returns the configured Supabase key without exposing it in logs."""
        if self.SUPABASE_KEY:
            val = self.SUPABASE_KEY.get_secret_value()
            if val and val.strip():
                return val.strip()
        return (
            os.getenv("SUPABASE_KEY")
            or os.getenv("SUPABASE_ANON_KEY")
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_SERVICE_KEY")
            or os.getenv("SUPABASE_API_KEY")
        )

    @property
    def jwt_secret(self) -> str:
        """
        Returns secret key used for signing session tokens.
        NO default or fallback is permitted outside test mode.
        """
        if self.AUTH_SECRET_KEY:
            val = self.AUTH_SECRET_KEY.get_secret_value().strip()
            if val:
                return val
        env_secret = os.getenv("AUTH_SECRET_KEY") or os.getenv("JWT_SECRET") or os.getenv("SECRET_KEY")
        if env_secret and env_secret.strip():
            return env_secret.strip()
        is_test_mode = (
            sys.modules.get("pytest") is not None
            or os.getenv("TESTING") == "1"
            or os.getenv("PYTEST_CURRENT_TEST") is not None
        )
        if is_test_mode:
            return "test_environment_secret_key_minimum_32_characters_long_for_pytest"
        raise ValueError("AUTH_SECRET_KEY is unset and no fallback is permitted outside test mode.")

    @model_validator(mode="after")
    def validate_auth_settings(self):
        """
        Validate AUTH_SECRET_KEY outside test mode.
        Fails fast at startup if unset or shorter than 32 characters.
        """
        is_test_mode = (
            sys.modules.get("pytest") is not None
            or os.getenv("TESTING") == "1"
            or os.getenv("PYTEST_CURRENT_TEST") is not None
        )
        if not is_test_mode:
            if not self.AUTH_SECRET_KEY or not self.AUTH_SECRET_KEY.get_secret_value().strip():
                raise ValueError(
                    "AUTH_SECRET_KEY is mandatory outside test mode. Set AUTH_SECRET_KEY in your environment or .env."
                )
            raw_secret = self.AUTH_SECRET_KEY.get_secret_value().strip()
            if len(raw_secret) < 32:
                raise ValueError(
                    f"AUTH_SECRET_KEY must be at least 32 characters long (got {len(raw_secret)} characters)."
                )
        return self

    @model_validator(mode="after")
    def validate_rag_settings(self):
        """
        Validate critical RAG and chunking invariants.
        """
        if self.CHUNK_OVERLAP_TOKENS >= self.CHUNK_SIZE_TOKENS:
            raise ValueError(
                f"CHUNK_OVERLAP_TOKENS ({self.CHUNK_OVERLAP_TOKENS}) must be strictly less than "
                f"CHUNK_SIZE_TOKENS ({self.CHUNK_SIZE_TOKENS})."
            )
        if self.TOP_K_CHUNKS > self.RETRIEVE_K:
            raise ValueError(
                f"TOP_K_CHUNKS ({self.TOP_K_CHUNKS}) must be less than or equal to "
                f"RETRIEVE_K ({self.RETRIEVE_K})."
            )
        if not (0.0 <= self.MIN_SIMILARITY <= 1.0):
            raise ValueError(
                f"MIN_SIMILARITY ({self.MIN_SIMILARITY}) must be between 0.0 and 1.0."
            )
        if self.MAX_UPLOAD_MB <= 0:
            raise ValueError("MAX_UPLOAD_MB must be greater than 0.")
        if self.MAX_PAGES <= 0:
            raise ValueError("MAX_PAGES must be greater than 0.")
        if self.EMBED_BATCH_SIZE <= 0:
            raise ValueError("EMBED_BATCH_SIZE must be greater than 0.")
        if self.LLM_MAX_TOKENS <= 0:
            raise ValueError("LLM_MAX_TOKENS must be greater than 0.")
        if not (0.0 <= self.LLM_TEMPERATURE <= 2.0):
            raise ValueError("LLM_TEMPERATURE must be between 0.0 and 2.0.")

        return self


settings = Settings()
