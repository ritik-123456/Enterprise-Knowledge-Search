import hashlib
import logging
import math
import re
import time
import uuid
from typing import List, Tuple, Optional, Dict, Any, Union

from pydantic import SecretStr
import qdrant_client
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    MatchAny,
    PayloadSchemaType
)

from app.core.config import settings
from app.schemas.rag import DocumentChunk, DocumentChunkInternal

logger = logging.getLogger(__name__)


class VectorStoreError(Exception):
    """Base exception for Vector Store operations."""
    pass


class VectorStoreConnectionError(VectorStoreError):
    """Raised when connecting or communicating with Qdrant fails."""
    pass


class CollectionModelMismatchError(VectorStoreError):
    """Raised when an existing Qdrant collection's embedding model or dimension differs from current config."""
    pass


class EmbeddingDimensionMismatchError(VectorStoreError):
    """Raised when an embedding vector dimension does not match collection configuration."""
    pass


KNOWN_MODEL_DIMENSIONS: Dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


def resolve_embedding_dimension(model_name: str) -> int:
    """Resolves vector dimension from embedding model identifier."""
    m = model_name.lower().strip()
    if m in KNOWN_MODEL_DIMENSIONS:
        return KNOWN_MODEL_DIMENSIONS[m]
    if "3-large" in m:
        return 3072
    if "3-small" in m or "ada-002" in m:
        return 1536
    return 1536


_shared_client: Optional[qdrant_client.QdrantClient] = None


def get_shared_client(
    url: Optional[str] = None,
    api_key: Optional[Union[str, SecretStr]] = None,
    path: Optional[str] = None,
    force_new: bool = False
) -> qdrant_client.QdrantClient:
    """
    Returns the shared QdrantClient singleton.
    If QDRANT_URL is set, connects to remote Qdrant (Cloud or Docker).
    Otherwise, uses local on-disk storage with path=QDRANT_PATH.
    """
    global _shared_client
    if _shared_client is not None and not force_new:
        return _shared_client

    active_url = url if url is not None else settings.QDRANT_URL
    active_key = api_key if api_key is not None else settings.QDRANT_API_KEY
    if isinstance(active_key, SecretStr):
        key_str = active_key.get_secret_value()
    else:
        key_str = str(active_key) if active_key else None

    if key_str and not key_str.strip():
        key_str = None

    active_path = path if path is not None else settings.QDRANT_PATH

    if active_url and str(active_url).strip():
        try:
            client = qdrant_client.QdrantClient(
                url=str(active_url).strip(),
                api_key=key_str,
                timeout=10.0,
                check_compatibility=False
            )
            # Verify connectivity
            client.get_collections()
            logger.info(f"Connected to Qdrant cluster at {active_url}")
        except Exception as e:
            logger.warning(
                f"Failed connecting to remote Qdrant at {active_url}: {e}. "
                f"Falling back to local on-disk storage at {active_path}."
            )
            client = qdrant_client.QdrantClient(
                path=active_path,
                check_compatibility=False
            )
    else:
        client = qdrant_client.QdrantClient(
            path=active_path,
            check_compatibility=False
        )
        logger.info(f"Initialized local on-disk Qdrant storage at {active_path}")

    _shared_client = client
    return client


class VectorStoreService:
    def __init__(
        self,
        client: Optional[qdrant_client.QdrantClient] = None,
        collection_name: Optional[str] = None,
        dimension: Optional[int] = None,
        embedding_model: Optional[str] = None,
        path: Optional[str] = None,
        url: Optional[str] = None,
        api_key: Optional[Union[str, SecretStr]] = None,
    ):
        self.collection_name = collection_name or settings.COLLECTION_NAME
        self.embedding_model = embedding_model or settings.EMBEDDING_MODEL
        self.dimension = dimension if dimension is not None else resolve_embedding_dimension(self.embedding_model)
        self.chunks_db: Dict[str, DocumentChunkInternal] = {}
        self.user_chunks_db: Dict[str, Dict[str, DocumentChunkInternal]] = {}

        if client is not None:
            self.client = client
        elif path is not None:
            self.client = qdrant_client.QdrantClient(path=path, check_compatibility=False)
        elif url is not None:
            key_val = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
            self.client = qdrant_client.QdrantClient(url=url, api_key=key_val, timeout=10.0, check_compatibility=False)
        else:
            self.client = get_shared_client()

        self._ensure_collection()

    def _retry_call(self, operation, max_retries: int = 3, retry_delay: float = 0.1):
        """
        Executes a Qdrant operation with retry backoff for transient failures.
        Does NOT retry validation or mismatch errors.
        """
        for attempt in range(1, max_retries + 1):
            try:
                return operation()
            except (CollectionModelMismatchError, EmbeddingDimensionMismatchError, ValueError):
                raise
            except Exception as e:
                if attempt < max_retries:
                    time.sleep(retry_delay * (2 ** (attempt - 1)))
                else:
                    logger.error(f"Qdrant operation failed after {max_retries} attempts: {e}")
                    raise VectorStoreConnectionError(
                        f"Failed communicating with Qdrant vector database: {e}"
                    ) from e

    def _ensure_collection(self) -> None:
        """
        Ensures the collection exists on startup with cosine distance and vector size
        derived from the embedding model's dimension.
        Stores embedding_model and dimension in collection metadata.
        If existing collection metadata differs from current config, raises CollectionModelMismatchError.
        """
        try:
            collections = self._retry_call(lambda: self.client.get_collections().collections)
            exists = any(c.name == self.collection_name for c in collections)
        except (CollectionModelMismatchError, EmbeddingDimensionMismatchError):
            raise
        except Exception as e:
            logger.error(f"Error checking collections in Qdrant: {e}")
            raise VectorStoreConnectionError(f"Failed to check collections in Qdrant: {e}") from e

        if not exists:
            try:
                self._retry_call(
                    lambda: self.client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=VectorParams(
                            size=self.dimension,
                            distance=Distance.COSINE
                        ),
                        metadata={
                            "embedding_model": self.embedding_model,
                            "dimension": self.dimension
                        }
                    )
                )
                logger.info(
                    f"Created Qdrant collection '{self.collection_name}' with "
                    f"dimension={self.dimension}, model='{self.embedding_model}'"
                )
            except (CollectionModelMismatchError, EmbeddingDimensionMismatchError):
                raise
            except Exception as e:
                logger.error(f"Failed to create collection '{self.collection_name}': {e}")
                raise VectorStoreConnectionError(f"Failed to create collection '{self.collection_name}': {e}") from e
        else:
            self._validate_existing_collection()

        self._ensure_payload_indexes()

    def _validate_existing_collection(self) -> None:
        """
        Validates that existing collection was configured with identical embedding model
        and dimension. Refuses to use collection with CollectionModelMismatchError if they differ.
        """
        try:
            info = self._retry_call(lambda: self.client.get_collection(self.collection_name))
        except Exception as e:
            raise VectorStoreConnectionError(f"Failed to retrieve info for collection '{self.collection_name}': {e}") from e

        vectors = info.config.params.vectors
        actual_dim = None
        if isinstance(vectors, VectorParams):
            actual_dim = vectors.size
        elif isinstance(vectors, dict) and "size" in vectors:
            actual_dim = vectors["size"]

        metadata = getattr(info.config, "metadata", {}) or {}
        meta_model = metadata.get("embedding_model")
        meta_dim = metadata.get("dimension") or actual_dim

        if meta_model is not None and meta_model != self.embedding_model:
            raise CollectionModelMismatchError(
                f"Collection '{self.collection_name}' was initialized with embedding model '{meta_model}', "
                f"but current configuration uses '{self.embedding_model}'. "
                f"Never mix embedding models in the same collection."
            )

        if meta_dim is not None and meta_dim != self.dimension:
            raise CollectionModelMismatchError(
                f"Collection '{self.collection_name}' has vector dimension {meta_dim}, "
                f"but current configuration requires {self.dimension} for model '{self.embedding_model}'. "
                f"Refusing to use collection to avoid incompatible vector dimensions."
            )

    def _ensure_payload_indexes(self) -> None:
        """Creates payload indexes on user_id, document_id, page_start, page_end, and pipeline_version."""
        # Ensure user_id tenant keyword index exists
        try:
            from qdrant_client.http.models import KeywordIndexParams
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="user_id",
                field_schema=KeywordIndexParams(type="keyword", is_tenant=True)
            )
        except Exception:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="user_id",
                    field_schema=PayloadSchemaType.KEYWORD
                )
            except Exception as e:
                logger.debug(f"Payload index creation notice for 'user_id': {e}")

        index_specs = [
            ("document_id", PayloadSchemaType.KEYWORD),
            ("pipeline_version", PayloadSchemaType.KEYWORD),
            ("page_start", PayloadSchemaType.INTEGER),
            ("page_end", PayloadSchemaType.INTEGER),
        ]
        for field_name, schema_type in index_specs:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=schema_type
                )
            except Exception as e:
                # Expected UserWarning or already exists notice
                logger.debug(f"Payload index creation notice for '{field_name}': {e}")

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Simple lowercase word tokenizer preserving technical terms, hyphens, and dots."""
        return re.findall(r'[a-zA-Z0-9_\-\.:/]{2,}', text.lower())

    @staticmethod
    def _token_index(token: str, dim: int) -> int:
        """Deterministic cross-process token index using MD5 hash."""
        return int(hashlib.md5(token.encode("utf-8")).hexdigest()[:8], 16) % dim

    def _generate_local_embedding(self, text: str, dimension: Optional[int] = None) -> List[float]:
        """
        Deterministic unit vector fallback respecting collection dimension.
        Ensures consistent, zero-dependency cross-process embedding calculation.
        """
        dim = dimension or self.dimension
        parts = text.split("\n", 1)
        if len(parts) == 2 and ">" in parts[0]:
            prefix, body = parts[0], parts[1]
            tokens_prefix = self._tokenize(prefix)
            tokens_body = self._tokenize(body)
            if not tokens_prefix and not tokens_body:
                return [0.0] * dim
            vector = [0.0] * dim
            for token in tokens_body:
                idx = self._token_index(token, dim)
                vector[idx] += 1.5
            for token in tokens_prefix:
                idx = self._token_index(token, dim)
                vector[idx] += 0.8
        else:
            tokens = self._tokenize(text)
            if not tokens:
                return [0.0] * dim
            vector = [0.0] * dim
            for token in tokens:
                idx = self._token_index(token, dim)
                vector[idx] += 1.0

        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector

    def generate_embedding(self, text: str) -> List[float]:
        """Generates embedding using OpenAI if configured (and not Gemini), otherwise fast local deterministic unit vector."""
        if settings.OPENAI_API_KEY and not settings.is_gemini:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=settings.OPENAI_API_KEY)
                resp = client.embeddings.create(
                    model=self.embedding_model,
                    input=text[:8000]
                )
                if resp.data and hasattr(resp.data[0], "embedding"):
                    emb = resp.data[0].embedding
                    if isinstance(emb, list) and len(emb) == self.dimension:
                        return emb
            except Exception as e:
                logger.warning(f"OpenAI embedding generation failed, using local fallback: {e}")

        return self._generate_local_embedding(text)

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generates embeddings in batches respecting EMBED_BATCH_SIZE."""
        if not texts:
            return []

        if settings.OPENAI_API_KEY and not settings.is_gemini:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=settings.OPENAI_API_KEY)
                results: List[List[float]] = []
                batch_size = max(1, settings.EMBED_BATCH_SIZE)
                for i in range(0, len(texts), batch_size):
                    batch_texts = [t[:8000] for t in texts[i:i + batch_size]]
                    resp = client.embeddings.create(
                        model=self.embedding_model,
                        input=batch_texts
                    )
                    results.extend([item.embedding for item in resp.data])
                return results
            except Exception as e:
                logger.warning(f"OpenAI batch embedding failed, using local fallback: {e}")

        return [self._generate_local_embedding(t) for t in texts]

    def add_document(self, document_id: str, chunks: List[DocumentChunk], user_id: str) -> None:
        """
        Indexes document chunks into Qdrant for a given document_id and user_id.
        Re-upload guarantees: first deletes existing points for (document_id, user_id),
        then upserts new chunks in batches of EMBED_BATCH_SIZE.
        If upsert fails partway, rolls back by deleting points for (document_id, user_id) so no half-indexed document remains.
        """
        if not user_id or not str(user_id).strip():
            raise ValueError("user_id is required to index documents")
        user_id = str(user_id).strip()

        # Step 1: Filtered delete of existing points for this document_id AND user_id
        self.delete_document(document_id, user_id=user_id)

        if not chunks:
            return

        # Step 2: Validate embedding dimensions and build PointStruct list
        points: List[PointStruct] = []
        texts_to_embed = []
        indices_needing_embed = []

        from app.services.chunking_service import get_embedding_text

        for idx, chunk in enumerate(chunks):
            chunk.user_id = user_id
            emb = getattr(chunk, "embedding", None)
            if emb is None:
                texts_to_embed.append(get_embedding_text(chunk))
                indices_needing_embed.append(idx)

        generated_embeddings: Dict[int, List[float]] = {}
        if texts_to_embed:
            batch_vectors = self.generate_embeddings_batch(texts_to_embed)
            for orig_idx, vec in zip(indices_needing_embed, batch_vectors):
                generated_embeddings[orig_idx] = vec

        for idx, chunk in enumerate(chunks):
            emb = getattr(chunk, "embedding", None)
            if emb is None:
                emb = generated_embeddings[idx]

            # Validate embedding dimension
            if len(emb) != self.dimension:
                raise EmbeddingDimensionMismatchError(
                    f"Embedding dimension {len(emb)} does not match collection dimension {self.dimension} "
                    f"for chunk '{chunk.chunk_id}'."
                )

            # Deterministic UUID5 point ID
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.chunk_id))
            source_name = getattr(chunk, "source_name", getattr(chunk, "document_name", ""))
            pipe_ver = getattr(chunk, "pipeline_version", "v1") or "v1"
            parent_txt = getattr(chunk, "parent_text", None)
            payload = {
                "chunk_id": chunk.chunk_id,
                "document_id": document_id,
                "user_id": user_id,
                "source_name": source_name,
                "document_name": getattr(chunk, "document_name", source_name),
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "section_heading": chunk.section_heading,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "token_count": chunk.token_count or 0,
                "content_hash": chunk.content_hash,
                "embedding_model": getattr(chunk, "embedding_model", self.embedding_model),
                "text": chunk.text,
                "pipeline_version": pipe_ver,
                "parent_text": parent_txt,
            }

            points.append(
                PointStruct(
                    id=point_id,
                    vector=emb,
                    payload=payload
                )
            )

            # Keep in-memory cache for backward-compatibility with endpoint tests
            internal = DocumentChunkInternal(
                document_id=document_id,
                user_id=user_id,
                chunk_id=chunk.chunk_id,
                document_name=payload["document_name"],
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_heading=chunk.section_heading,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                token_count=chunk.token_count or 0,
                content_hash=chunk.content_hash,
                embedding_model=payload["embedding_model"],
                text=chunk.text,
                embedding=emb,
                pipeline_version=pipe_ver,
                parent_text=parent_txt
            )
            self.chunks_db[chunk.chunk_id] = internal
            self.user_chunks_db.setdefault(user_id, {})[chunk.chunk_id] = internal

        # Step 3: Batch upsert with rollback on failure
        batch_size = max(1, settings.EMBED_BATCH_SIZE)
        try:
            for i in range(0, len(points), batch_size):
                batch = points[i:i + batch_size]
                self._retry_call(
                    lambda b=batch: self.client.upsert(
                        collection_name=self.collection_name,
                        points=b
                    )
                )
        except Exception as exc:
            logger.error(
                f"Batch upsert failed for document '{document_id}' (user '{user_id}'): {exc}. "
                f"Rolling back partially indexed points."
            )
            try:
                self.delete_document(document_id, user_id=user_id)
            except Exception as rollback_err:
                logger.error(f"Rollback failed for document '{document_id}': {rollback_err}")
            raise exc

    def delete_document(self, document_id: str, user_id: str) -> None:
        """Deletes all points in Qdrant associated with document_id AND user_id."""
        if not user_id or not str(user_id).strip():
            raise ValueError("user_id is required to delete documents")
        user_id = str(user_id).strip()

        del_filter = Filter(
            must=[
                FieldCondition(
                    key="document_id",
                    match=MatchValue(value=document_id)
                ),
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value=user_id)
                )
            ]
        )
        try:
            self._retry_call(
                lambda: self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=del_filter
                )
            )
        except Exception as e:
            logger.error(f"Failed deleting points for document '{document_id}' (user '{user_id}'): {e}")
            raise VectorStoreConnectionError(f"Failed to delete document '{document_id}': {e}") from e

        # Clear matching entries from chunks_db
        to_del = [
            k for k, v in self.chunks_db.items()
            if getattr(v, "document_id", None) == document_id and getattr(v, "user_id", None) == user_id
        ]
        for cid in to_del:
            self.chunks_db.pop(cid, None)
        if user_id in self.user_chunks_db:
            u_to_del = [
                k for k, v in self.user_chunks_db[user_id].items()
                if getattr(v, "document_id", None) == document_id
            ]
            for cid in u_to_del:
                self.user_chunks_db[user_id].pop(cid, None)

    def clear_user_documents(self, user_id: str) -> None:
        """Deletes all points in Qdrant associated with user_id."""
        if not user_id or not str(user_id).strip():
            raise ValueError("user_id is required to clear user documents")
        user_id = str(user_id).strip()
        del_filter = Filter(
            must=[
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value=user_id)
                )
            ]
        )
        try:
            self._retry_call(
                lambda: self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=del_filter
                )
            )
        except Exception as e:
            logger.error(f"Failed clearing points for user '{user_id}': {e}")
            raise VectorStoreConnectionError(f"Failed to clear points for user '{user_id}': {e}") from e

        # Clear matching entries from chunks_db
        to_del = [k for k, v in self.chunks_db.items() if getattr(v, "user_id", None) == user_id]
        for cid in to_del:
            self.chunks_db.pop(cid, None)
        self.user_chunks_db.pop(user_id, None)

    def list_documents(self, user_id: str) -> List[str]:
        """Lists distinct document_ids present in the collection for a specific user_id."""
        if not user_id or not str(user_id).strip():
            raise ValueError("user_id is required to list documents")
        user_id = str(user_id).strip()
        user_filter = Filter(
            must=[
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value=user_id)
                )
            ]
        )
        doc_ids = set()
        offset = None
        while True:
            try:
                points, offset = self._retry_call(
                    lambda off=offset: self.client.scroll(
                        collection_name=self.collection_name,
                        scroll_filter=user_filter,
                        offset=off,
                        limit=100,
                        with_payload=["document_id", "user_id"]
                    )
                )
            except Exception as e:
                raise VectorStoreConnectionError(f"Failed to list documents for user '{user_id}': {e}") from e

            for p in points:
                if p.payload and "document_id" in p.payload:
                    doc_ids.add(str(p.payload["document_id"]))
            if offset is None:
                break
        return sorted(list(doc_ids))

    def count(self) -> int:
        """Returns total count of points stored in the collection."""
        try:
            res = self._retry_call(
                lambda: self.client.count(
                    collection_name=self.collection_name,
                    exact=True
                )
            )
            return res.count
        except Exception as e:
            raise VectorStoreConnectionError(f"Failed to count points in collection: {e}") from e

    def sync_chunks_from_storage(self, user_id: Optional[str] = None) -> None:
        """Loads chunks from Qdrant Cloud into chunks_db in-memory cache, optionally filtered by user_id."""
        try:
            scroll_filter = None
            if user_id:
                scroll_filter = Filter(
                    must=[
                        FieldCondition(
                            key="user_id",
                            match=MatchValue(value=str(user_id).strip())
                        )
                    ]
                )
            offset = None
            while True:
                points, offset = self._retry_call(
                    lambda off=offset: self.client.scroll(
                        collection_name=self.collection_name,
                        scroll_filter=scroll_filter,
                        offset=off,
                        limit=100,
                        with_payload=True,
                        with_vectors=False
                    )
                )
                for p in points:
                    if p.payload and "chunk_id" in p.payload:
                        payload = dict(p.payload)
                        if "document_name" not in payload and "source_name" in payload:
                            payload["document_name"] = payload["source_name"]
                        if "source_name" not in payload and "document_name" in payload:
                            payload["source_name"] = payload["document_name"]
                        chunk = DocumentChunk(**payload)
                        self.chunks_db[chunk.chunk_id] = chunk
                        uid = getattr(chunk, "user_id", None) or user_id
                        if uid:
                            self.user_chunks_db.setdefault(str(uid), {})[chunk.chunk_id] = chunk
                if offset is None:
                    break
        except Exception as e:
            logger.warning(f"Could not sync chunks from Qdrant: {e}")

    def search(
        self,
        user_id: str,
        query_embedding: Optional[Union[List[float], str]] = None,
        k: Optional[int] = None,
        document_id: Optional[str] = None,
        *,
        query: Optional[str] = None,
        retrieve_k: Optional[int] = None,
        top_k: Optional[int] = None,
        min_similarity: Optional[float] = None,
        doc_filter: Optional[List[str]] = None,
        pipeline_version: Optional[str] = None,
    ) -> List[Tuple[DocumentChunk, float]]:
        """
        Searches collection with query vector or text query strictly scoped to user_id.
        - Enforces user_id requirement (never queries without user_id)
        - Applies limit=k (defaulting to RETRIEVE_K)
        - Optional document_id filter
        - Drops results with score below MIN_SIMILARITY
        - Returns public DocumentChunk objects plus score (embeddings strictly stripped).
        - Empty collection returns [] without error.
        """
        if not user_id or not str(user_id).strip():
            raise ValueError("user_id is required for vector search")
        user_id = str(user_id).strip()

        # Resolve query vector
        if query_embedding is not None:
            if isinstance(query_embedding, list):
                query_vec = query_embedding
            else:
                query_vec = self.generate_embedding(str(query_embedding))
        elif query is not None:
            query_vec = self.generate_embedding(query)
        else:
            raise ValueError("search requires query_embedding (list of floats) or query (string).")

        # Validate query embedding dimension
        if len(query_vec) != self.dimension:
            raise EmbeddingDimensionMismatchError(
                f"Query embedding dimension {len(query_vec)} does not match collection dimension {self.dimension}."
            )

        limit = k if k is not None else (retrieve_k if retrieve_k is not None else (top_k if top_k is not None else settings.RETRIEVE_K))
        cutoff = min_similarity if min_similarity is not None else settings.MIN_SIMILARITY
        score_thresh = cutoff if (cutoff is not None and cutoff > 0.0) else None

        # Mandatory user_id filter: every query MUST be constrained by user_id
        must_conditions = [
            FieldCondition(
                key="user_id",
                match=MatchValue(value=user_id)
            )
        ]
        must_not_conditions = []
        if document_id:
            must_conditions.append(
                FieldCondition(
                    key="document_id",
                    match=MatchValue(value=document_id)
                )
            )
        if doc_filter:
            must_conditions.append(
                FieldCondition(
                    key="document_name",
                    match=MatchAny(any=doc_filter)
                )
            )
        if pipeline_version == "v1":
            must_conditions.append(
                FieldCondition(
                    key="pipeline_version",
                    match=MatchValue(value="v1")
                )
            )
        elif pipeline_version == "v2":
            # Under v2, match both explicitly tagged 'v2' and untagged pre-existing chunks
            must_not_conditions.append(
                FieldCondition(
                    key="pipeline_version",
                    match=MatchValue(value="v1")
                )
            )

        filter_kwargs = {}
        if must_conditions:
            filter_kwargs["must"] = must_conditions
        if must_not_conditions:
            filter_kwargs["must_not"] = must_not_conditions

        q_filter = Filter(**filter_kwargs) if filter_kwargs else None

        results: List[Tuple[DocumentChunk, float]] = []

        try:
            resp = self._retry_call(
                lambda: self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_vec,
                    limit=limit,
                    score_threshold=score_thresh,
                    query_filter=q_filter
                )
            )
            for point in resp.points:
                score = float(point.score)
                if score_thresh is not None and score < score_thresh:
                    continue

                payload = dict(point.payload or {})
                if "document_name" not in payload and "source_name" in payload:
                    payload["document_name"] = payload["source_name"]
                elif "source_name" not in payload and "document_name" in payload:
                    payload["source_name"] = payload["document_name"]
                if "embedding_model" not in payload:
                    payload["embedding_model"] = self.embedding_model

                # Create public DocumentChunk (does NOT include embedding)
                chunk = DocumentChunk(**payload)
                results.append((chunk, score))
        except (EmbeddingDimensionMismatchError, CollectionModelMismatchError):
            raise
        except Exception as e:
            logger.warning(f"Qdrant query failed: {e}")
            if not self.chunks_db:
                raise VectorStoreConnectionError(f"Failed to query Qdrant: {e}") from e

        # Fallback to in-memory cache if Qdrant returned nothing but chunks_db has items (e.g. manual test mock)
        if not results and (self.user_chunks_db.get(user_id) or self.chunks_db) and self.count() == 0:
            user_cached = self.user_chunks_db.get(user_id, {})
            candidate_chunks = user_cached.values() if user_cached else [
                c for c in self.chunks_db.values() if getattr(c, "user_id", None) == user_id
            ]
            for internal_chunk in candidate_chunks:
                if document_id and internal_chunk.document_id != document_id:
                    continue
                if doc_filter and internal_chunk.document_name not in doc_filter:
                    continue
                if pipeline_version == "v1" and getattr(internal_chunk, "pipeline_version", "v1") != "v1":
                    continue
                if pipeline_version == "v2" and getattr(internal_chunk, "pipeline_version", "v2") == "v1":
                    continue
                sim = self._cosine_similarity(query_vec, getattr(internal_chunk, "embedding", None) or [])
                if sim >= cutoff:
                    chunk_obj = internal_chunk.to_public() if hasattr(internal_chunk, "to_public") else internal_chunk
                    results.append((chunk_obj, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        if top_k is not None and len(results) > top_k:
            results = results[:top_k]

        return results

    @staticmethod
    def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """Calculates cosine similarity between two unit/arbitrary vectors."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        return max(0.0, min(1.0, dot_product / (norm_a * norm_b)))

    def add_chunks(self, chunks: List[DocumentChunk], user_id: Optional[str] = None) -> None:
        """Indexes arbitrary chunks, grouping them by document_id."""
        if not chunks:
            return
        grouped: Dict[str, List[DocumentChunk]] = {}
        for c in chunks:
            grouped.setdefault(c.document_id, []).append(c)
        for doc_id, doc_chunks in grouped.items():
            uid = user_id or getattr(doc_chunks[0], "user_id", None) or "default_user"
            self.add_document(doc_id, doc_chunks, user_id=uid)

    def clear(self) -> None:
        """Clears all points and in-memory cache."""
        self.chunks_db.clear()
        self.user_chunks_db.clear()
        try:
            self.client.delete_collection(collection_name=self.collection_name)
        except Exception:
            pass
        self._ensure_collection()


vector_store = VectorStoreService()
