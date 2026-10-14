import hashlib
import math
from datetime import datetime, timezone
from typing import List, Optional
from unittest.mock import patch

import pytest
import qdrant_client

from app.schemas.rag import DocumentChunk, DocumentChunkInternal
from app.services.vector_store import (
    VectorStoreService,
    CollectionModelMismatchError,
    EmbeddingDimensionMismatchError,
    VectorStoreConnectionError
)


def normalize(vec: List[float]) -> List[float]:
    """Helper to return unit vector for cosine distance tests."""
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm > 0 else vec


def make_test_chunk(
    document_id: str,
    chunk_index: int,
    text: str,
    embedding: Optional[List[float]] = None,
    document_name: str = "handbook.pdf",
    page_start: int = 1,
    page_end: int = 1,
    model_name: str = "test-model"
) -> DocumentChunkInternal:
    """Creates a DocumentChunkInternal with metadata and embedding for vector store tests."""
    return DocumentChunkInternal(
        document_id=document_id,
        chunk_id=f"{document_id}_p{page_start}_c{chunk_index:03d}",
        document_name=document_name,
        page_start=page_start,
        page_end=page_end,
        section_heading="Test Section",
        char_start=chunk_index * 100,
        char_end=(chunk_index + 1) * 100,
        token_count=len(text.split()),
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        embedding_model=model_name,
        created_at=datetime.now(timezone.utc),
        text=text,
        embedding=embedding
    )


def test_ranking_order(tmp_path):
    """
    Test 1: Ranking order.
    Query results must be sorted strictly in descending order of similarity score.
    """
    client = qdrant_client.QdrantClient(path=str(tmp_path))
    dim = 4
    store = VectorStoreService(
        client=client,
        collection_name="test_ranking",
        dimension=dim,
        embedding_model="test-model"
    )

    query_vec = [1.0, 0.0, 0.0, 0.0]

    chunk_top = make_test_chunk("doc1", 0, "Top match text", normalize([0.98, 0.1, 0.0, 0.0]))
    chunk_mid = make_test_chunk("doc1", 1, "Mid match text", normalize([0.70, 0.70, 0.0, 0.0]))
    chunk_low = make_test_chunk("doc1", 2, "Low match text", normalize([0.40, 0.90, 0.0, 0.0]))

    store.add_document("doc1", [chunk_top, chunk_mid, chunk_low])

    results = store.search(query_embedding=query_vec, k=10, min_similarity=0.1)

    assert len(results) == 3
    # Check strict descending ranking
    assert results[0][0].chunk_id == chunk_top.chunk_id
    assert results[1][0].chunk_id == chunk_mid.chunk_id
    assert results[2][0].chunk_id == chunk_low.chunk_id

    # Verify score monotonicity
    assert results[0][1] > results[1][1] > results[2][1]
    client.close()


def test_min_similarity_cutoff(tmp_path):
    """
    Test 2: MIN_SIMILARITY cutoff.
    Results with similarity scores below the threshold must be filtered out.
    """
    client = qdrant_client.QdrantClient(path=str(tmp_path))
    dim = 4
    store = VectorStoreService(
        client=client,
        collection_name="test_cutoff",
        dimension=dim,
        embedding_model="test-model"
    )

    query_vec = [1.0, 0.0, 0.0, 0.0]

    chunk_high = make_test_chunk("doc_cut", 0, "High relevance", normalize([0.95, 0.1, 0.0, 0.0]))
    chunk_mid = make_test_chunk("doc_cut", 1, "Medium relevance", normalize([0.60, 0.80, 0.0, 0.0]))
    chunk_low = make_test_chunk("doc_cut", 2, "Low relevance below cutoff", normalize([0.15, 0.95, 0.0, 0.0]))

    store.add_document("doc_cut", [chunk_high, chunk_mid, chunk_low])

    # Search with threshold 0.50 -> chunk_low must be dropped
    results = store.search(query_embedding=query_vec, k=10, min_similarity=0.50)

    returned_ids = [r[0].chunk_id for r in results]
    assert chunk_high.chunk_id in returned_ids
    assert chunk_mid.chunk_id in returned_ids
    assert chunk_low.chunk_id not in returned_ids

    for _, score in results:
        assert score >= 0.50

    client.close()


def test_document_id_filter(tmp_path):
    """
    Test 3: document_id filter.
    Queries filtered by document_id must only return chunks for that document.
    """
    client = qdrant_client.QdrantClient(path=str(tmp_path))
    dim = 4
    store = VectorStoreService(
        client=client,
        collection_name="test_filter",
        dimension=dim,
        embedding_model="test-model"
    )

    query_vec = [1.0, 0.0, 0.0, 0.0]

    chunks_doc_a = [
        make_test_chunk("doc_alpha", 0, "Alpha chunk 1", normalize([0.9, 0.1, 0.0, 0.0])),
        make_test_chunk("doc_alpha", 1, "Alpha chunk 2", normalize([0.8, 0.2, 0.0, 0.0])),
    ]
    chunks_doc_b = [
        make_test_chunk("doc_beta", 0, "Beta chunk 1", normalize([0.95, 0.05, 0.0, 0.0])),
    ]

    store.add_document("doc_alpha", chunks_doc_a)
    store.add_document("doc_beta", chunks_doc_b)

    # Search with document_id filter for doc_alpha
    results_alpha = store.search(query_embedding=query_vec, k=10, document_id="doc_alpha", min_similarity=0.1)
    assert len(results_alpha) == 2
    for chunk, _ in results_alpha:
        assert chunk.document_id == "doc_alpha"

    # Search with document_id filter for doc_beta
    results_beta = store.search(query_embedding=query_vec, k=10, document_id="doc_beta", min_similarity=0.1)
    assert len(results_beta) == 1
    assert results_beta[0][0].document_id == "doc_beta"

    client.close()


def test_replace_without_duplicates_reupload(tmp_path):
    """
    Test 4: Replace without duplicates on re-upload.
    Re-uploading the same document_id must replace previous chunks without leaving orphaned duplicates.
    """
    client = qdrant_client.QdrantClient(path=str(tmp_path))
    dim = 4
    store = VectorStoreService(
        client=client,
        collection_name="test_reupload",
        dimension=dim,
        embedding_model="test-model"
    )

    # Upload version 1 (2 chunks)
    v1_chunks = [
        make_test_chunk("doc_v", 0, "V1 chunk 0", normalize([1.0, 0.0, 0.0, 0.0])),
        make_test_chunk("doc_v", 1, "V1 chunk 1", normalize([0.9, 0.1, 0.0, 0.0])),
    ]
    store.add_document("doc_v", v1_chunks)
    assert store.count() == 2
    assert store.list_documents() == ["doc_v"]

    # Re-upload version 2 (3 new chunks)
    v2_chunks = [
        make_test_chunk("doc_v", 10, "V2 chunk 10", normalize([0.95, 0.05, 0.0, 0.0])),
        make_test_chunk("doc_v", 11, "V2 chunk 11", normalize([0.85, 0.15, 0.0, 0.0])),
        make_test_chunk("doc_v", 12, "V2 chunk 12", normalize([0.75, 0.25, 0.0, 0.0])),
    ]
    store.add_document("doc_v", v2_chunks)

    # Total count must be exactly 3, not 5 (no duplicates)
    assert store.count() == 3
    assert store.list_documents() == ["doc_v"]

    # Old chunk IDs must not exist anymore
    results = store.search(query_embedding=[1.0, 0.0, 0.0, 0.0], k=10, min_similarity=0.1)
    found_chunk_ids = {r[0].chunk_id for r in results}
    assert found_chunk_ids == {c.chunk_id for c in v2_chunks}
    assert v1_chunks[0].chunk_id not in found_chunk_ids
    assert v1_chunks[1].chunk_id not in found_chunk_ids

    client.close()


def test_delete_document(tmp_path):
    """
    Test 5: delete_document.
    Deleting a document must remove all of its points while leaving other documents untouched.
    """
    client = qdrant_client.QdrantClient(path=str(tmp_path))
    dim = 4
    store = VectorStoreService(
        client=client,
        collection_name="test_delete",
        dimension=dim,
        embedding_model="test-model"
    )

    doc1_chunks = [
        make_test_chunk("doc_to_delete", 0, "Doc1 chunk", normalize([1.0, 0.0, 0.0, 0.0]))
    ]
    doc2_chunks = [
        make_test_chunk("doc_to_keep", 0, "Doc2 chunk", normalize([0.0, 1.0, 0.0, 0.0]))
    ]

    store.add_document("doc_to_delete", doc1_chunks)
    store.add_document("doc_to_keep", doc2_chunks)
    assert store.count() == 2
    assert set(store.list_documents()) == {"doc_to_delete", "doc_to_keep"}

    # Delete doc_to_delete
    store.delete_document("doc_to_delete")

    assert store.count() == 1
    assert store.list_documents() == ["doc_to_keep"]

    # Searching for doc_to_delete yields empty
    results = store.search(query_embedding=[1.0, 0.0, 0.0, 0.0], k=10, document_id="doc_to_delete", min_similarity=0.1)
    assert results == []

    # Doc to keep is still present
    results_keep = store.search(query_embedding=[0.0, 1.0, 0.0, 0.0], k=10, document_id="doc_to_keep", min_similarity=0.1)
    assert len(results_keep) == 1

    client.close()


def test_empty_collection(tmp_path):
    """
    Test 6: Empty collection handling.
    Searching, listing, or counting an empty collection must return empty results without error.
    """
    client = qdrant_client.QdrantClient(path=str(tmp_path))
    dim = 4
    store = VectorStoreService(
        client=client,
        collection_name="test_empty",
        dimension=dim,
        embedding_model="test-model"
    )

    assert store.count() == 0
    assert store.list_documents() == []

    results = store.search(query_embedding=[1.0, 0.0, 0.0, 0.0], k=5)
    assert results == []

    client.close()


def test_model_and_dimension_mismatch_refusal(tmp_path):
    """
    Test 7: Model & dimension mismatch refusal.
    Attempting to open an existing collection with a differing model or dimension
    must refuse to use the collection by raising CollectionModelMismatchError.
    """
    client = qdrant_client.QdrantClient(path=str(tmp_path))
    col_name = "test_mismatch"

    # 1. Initialize collection with model A and dim 4
    store1 = VectorStoreService(
        client=client,
        collection_name=col_name,
        dimension=4,
        embedding_model="text-embedding-3-small"
    )
    store1.add_document("d1", [make_test_chunk("d1", 0, "text", [1.0, 0.0, 0.0, 0.0])])

    # 2. Refuse when embedding_model differs (even if dim were the same)
    with pytest.raises(CollectionModelMismatchError) as exc_model:
        VectorStoreService(
            client=client,
            collection_name=col_name,
            dimension=4,
            embedding_model="text-embedding-3-large"  # Different model
        )
    assert "Never mix embedding models" in str(exc_model.value) or "Refusing to use collection" in str(exc_model.value)

    # 3. Refuse when dimension differs
    with pytest.raises(CollectionModelMismatchError) as exc_dim:
        VectorStoreService(
            client=client,
            collection_name=col_name,
            dimension=128,  # Different dimension
            embedding_model="text-embedding-3-small"
        )
    assert "incompatible vector dimensions" in str(exc_dim.value) or "dimension" in str(exc_dim.value)

    client.close()


def test_no_embedding_leaked_in_public_output(tmp_path):
    """
    Test 8: No embedding leaked in public output.
    Returned search results must be public DocumentChunk instances without embedding attributes or payload leakage.
    """
    client = qdrant_client.QdrantClient(path=str(tmp_path))
    dim = 4
    store = VectorStoreService(
        client=client,
        collection_name="test_no_leak",
        dimension=dim,
        embedding_model="test-model"
    )

    secret_emb = [0.8, 0.6, 0.0, 0.0]
    chunk = make_test_chunk("doc_safe", 0, "Confidential document text", secret_emb)
    store.add_document("doc_safe", [chunk])

    # Search via public interface
    results = store.search(query_embedding=[1.0, 0.0, 0.0, 0.0], k=5, min_similarity=0.1)
    assert len(results) == 1

    retrieved_chunk, score = results[0]
    assert isinstance(retrieved_chunk, DocumentChunk)

    # Must NOT have embedding attribute
    assert not hasattr(retrieved_chunk, "embedding")

    # Serialized model dump must NOT contain embedding key
    dump = retrieved_chunk.model_dump()
    assert "embedding" not in dump

    # Check Qdrant point payload directly: payload must never contain raw embedding vector
    scroll_res, _ = client.scroll("test_no_leak", limit=5, with_vectors=True)
    for pt in scroll_res:
        assert "embedding" not in pt.payload
        # Verify vector is stored in the vector field, not payload
        assert pt.vector is not None
        assert pt.payload["document_id"] == "doc_safe"

    client.close()


def test_data_surviving_client_restart(tmp_path):
    """
    Test 9: Data surviving a client restart.
    Data written to on-disk Qdrant storage must persist and remain retrievable after the client is closed and reopened.
    """
    storage_path = str(tmp_path / "qdrant_persisted")
    dim = 4
    col_name = "test_persistence"

    # Session 1: Write data and close client
    client1 = qdrant_client.QdrantClient(path=storage_path)
    store1 = VectorStoreService(
        client=client1,
        collection_name=col_name,
        dimension=dim,
        embedding_model="persist-model"
    )

    doc_chunks = [
        make_test_chunk("doc_persist", 0, "Persisted knowledge article 1", normalize([1.0, 0.0, 0.0, 0.0])),
        make_test_chunk("doc_persist", 1, "Persisted knowledge article 2", normalize([0.0, 1.0, 0.0, 0.0])),
    ]
    store1.add_document("doc_persist", doc_chunks)
    assert store1.count() == 2
    client1.close()

    # Session 2: Reopen on-disk storage with new client instance
    client2 = qdrant_client.QdrantClient(path=storage_path)
    store2 = VectorStoreService(
        client=client2,
        collection_name=col_name,
        dimension=dim,
        embedding_model="persist-model"
    )

    # Check that count and list_documents survived restart
    assert store2.count() == 2
    assert store2.list_documents() == ["doc_persist"]

    # Check that vector search functions properly on persisted data
    results = store2.search(query_embedding=[1.0, 0.0, 0.0, 0.0], k=5, min_similarity=0.5)
    assert len(results) == 1
    assert results[0][0].chunk_id == doc_chunks[0].chunk_id
    assert results[0][0].text == "Persisted knowledge article 1"

    client2.close()


def test_upsert_failure_rollback(tmp_path):
    """
    Test 10: Upsert failure rollback.
    If batch upsert fails partway, any points for that document_id must be deleted so no half-indexed document remains.
    """
    client = qdrant_client.QdrantClient(path=str(tmp_path))
    dim = 4
    store = VectorStoreService(
        client=client,
        collection_name="test_rollback",
        dimension=dim,
        embedding_model="test-model"
    )

    chunks = [
        make_test_chunk("doc_fail", 0, "Part 1", [1.0, 0.0, 0.0, 0.0]),
        make_test_chunk("doc_fail", 1, "Part 2", [0.0, 1.0, 0.0, 0.0]),
    ]

    original_upsert = client.upsert
    call_count = 0

    def fail_on_second_batch(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise RuntimeError("Simulated network failure on batch 2")
        return original_upsert(*args, **kwargs)

    with patch.object(store.client, "upsert", side_effect=fail_on_second_batch):
        with patch("app.services.vector_store.settings.EMBED_BATCH_SIZE", 1):
            with pytest.raises((VectorStoreConnectionError, RuntimeError)):
                store.add_document("doc_fail", chunks)

    # Document must not remain partially indexed
    assert store.count() == 0
    assert store.list_documents() == []

    client.close()


def test_dimension_validation_before_upsert_and_search(tmp_path):
    """
    Test 11: Validation of embedding dimension.
    Embedding vector dimension must match collection dimension before upserting or searching.
    """
    client = qdrant_client.QdrantClient(path=str(tmp_path))
    dim = 4
    store = VectorStoreService(
        client=client,
        collection_name="test_dim_val",
        dimension=dim,
        embedding_model="test-model"
    )

    # Chunk with 5-dim vector on 4-dim collection
    invalid_chunk = make_test_chunk("doc_bad", 0, "Bad vector", [1.0, 0.0, 0.0, 0.0, 0.0])
    with pytest.raises(EmbeddingDimensionMismatchError) as exc_upsert:
        store.add_document("doc_bad", [invalid_chunk])
    assert "does not match collection dimension" in str(exc_upsert.value)

    # Search with 3-dim query vector on 4-dim collection
    with pytest.raises(EmbeddingDimensionMismatchError) as exc_search:
        store.search(query_embedding=[1.0, 0.0, 0.0])
    assert "does not match collection dimension" in str(exc_search.value)

    client.close()
