"""
Pytest Test Suite: Multi-Tenant Document Isolation
Tests strict server-enforced tenant isolation across authentication,
vector store, BM25 retriever, document CRUD, and RAG question answering.
"""

import io
import time
import pytest
import uuid
import jwt
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.auth_dependency import create_access_token
from app.core.rate_limiter import upload_rate_limiter
from app.api.rag import user_document_store
from app.services.vector_store import vector_store
from app.services.hybrid_retriever import corpus_bm25_index
from app.schemas.rag import DocumentChunk

client = TestClient(app)

USER_A_ID = "user_alpha_111"
USER_B_ID = "user_bravo_222"

TEST_COLLECTION_NAME = f"test_isolation_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="session", autouse=True)
def setup_isolated_test_collection():
    """Points vector_store to a dedicated temporary test collection and cleans it up afterwards."""
    orig_col = vector_store.collection_name
    vector_store.collection_name = TEST_COLLECTION_NAME
    vector_store._ensure_collection()
    yield
    try:
        vector_store.client.delete_collection(TEST_COLLECTION_NAME)
    except Exception:
        pass
    vector_store.collection_name = orig_col


def generate_test_token(user_id: str, email: str = "test@example.com", expired: bool = False) -> str:
    """Helper to create valid or expired signed JWT tokens."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "name": f"User {user_id}",
        "role": "Member",
        "department": "Engineering",
        "iat": now - 7200 if expired else now,
        "exp": now - 3600 if expired else now + 3600
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def make_dummy_pdf(content: str = "Standard dummy text for enterprise testing") -> io.BytesIO:
    """Creates a minimal valid PDF with > 100 characters so pdf_service does not trigger OCR fallback."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    full_text = (
        f"ENTERPRISE PLATFORM RUNBOOK & POLICY DOCUMENT\n\n"
        f"This document defines the operational standards and technical protocols.\n"
        f"Section 1. Operational Overview: {content}\n"
        f"All system engineers must verify procedures prior to deployment.\n"
        f"Confidentiality notice: Proprietary and private enterprise intelligence.\n"
    )
    page.insert_text((50, 72), full_text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    buf.seek(0)
    return buf


@pytest.fixture(autouse=True)
def clean_stores():
    """Ensure vector store and BM25 index are clean before and after tests."""
    vector_store.clear()
    corpus_bm25_index._user_corpora.clear()
    user_document_store.clear()
    upload_rate_limiter.clear()
    yield
    vector_store.clear()
    corpus_bm25_index._user_corpora.clear()
    user_document_store.clear()
    upload_rate_limiter.clear()


# ============================================================================
# 1. AUTH ENFORCEMENT & FORGED/EXPIRED TOKEN REJECTION
# ============================================================================

def test_endpoints_require_auth_no_token_returns_401():
    """All /api/documents/* endpoints return 401 when no token is supplied."""
    endpoints = [
        ("GET", "/api/documents"),
        ("POST", "/api/documents/upload"),
        ("GET", "/api/documents/some_doc_id/status"),
        ("DELETE", "/api/documents/some_doc_id"),
        ("POST", "/api/documents/some_doc_id/reindex"),
        ("POST", "/api/documents/ask"),
        ("GET", "/api/documents/chunks"),
        ("DELETE", "/api/documents/clear"),
    ]

    for method, path in endpoints:
        if method == "GET":
            resp = client.get(path)
        elif method == "POST":
            resp = client.post(path, json={"question": "test"} if path.endswith("/ask") else {})
        elif method == "DELETE":
            resp = client.delete(path)
        assert resp.status_code == 401, f"{method} {path} did not return 401 without token (got {resp.status_code})"


def test_endpoints_reject_forged_and_expired_tokens():
    """Endpoints return 401 when presented with forged or expired bearer tokens."""
    expired_token = generate_test_token(USER_A_ID, expired=True)
    forged_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.bogus_signature_abc123"

    for bad_token in [expired_token, forged_token]:
        headers = {"Authorization": f"Bearer {bad_token}"}
        resp_get = client.get("/api/documents", headers=headers)
        assert resp_get.status_code == 401

        resp_ask = client.post("/api/documents/ask", headers=headers, json={"question": "What is policy?"})
        assert resp_ask.status_code == 401

        resp_clear = client.delete("/api/documents/clear", headers=headers)
        assert resp_clear.status_code == 401


# ============================================================================
# 2. X-USER-ID HEADER IS STRICTLY IGNORED
# ============================================================================

def test_x_user_id_header_is_ignored():
    """
    Sending X-User-Id: <A's id> with no token returns 401.
    Sending X-User-Id: <A's id> with B's token only queries B's tenancy.
    """
    # 1. No token + X-User-Id -> 401
    resp = client.get("/api/documents", headers={"X-User-Id": USER_A_ID})
    assert resp.status_code == 401

    # 2. Add document for User A
    token_a = generate_test_token(USER_A_ID)
    pdf_stream = make_dummy_pdf("User A private secret handbook")
    upload_resp = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"file": ("handbook_a.pdf", pdf_stream, "application/pdf")}
    )
    assert upload_resp.status_code == 201

    # 3. User B calls GET /api/documents with X-User-Id: USER_A_ID
    token_b = generate_test_token(USER_B_ID)
    resp_b = client.get(
        "/api/documents",
        headers={
            "Authorization": f"Bearer {token_b}",
            "X-User-Id": USER_A_ID
        }
    )
    assert resp_b.status_code == 200
    docs = resp_b.json()
    # Must NOT return User A's documents
    assert len(docs) == 0


# ============================================================================
# 3. VECTOR STORE SEARCH REQUIRES USER_ID
# ============================================================================

def test_vector_store_search_raises_if_user_id_missing():
    """vector_store.search() MUST raise ValueError if user_id is empty, None, or whitespace."""
    with pytest.raises(ValueError, match="user_id is required"):
        vector_store.search(query="query", user_id="")

    with pytest.raises(ValueError, match="user_id is required"):
        vector_store.search(query="query", user_id=None)

    with pytest.raises(ValueError, match="user_id is required"):
        vector_store.search(query="query", user_id="   ")


# ============================================================================
# 4. TENANT ISOLATION: UPLOAD, LISTING, DELETION
# ============================================================================

def test_user_a_uploads_doc_user_b_cannot_see_it():
    """User A uploads a doc; User B's GET /documents does not include it."""
    token_a = generate_test_token(USER_A_ID)
    token_b = generate_test_token(USER_B_ID)

    pdf_stream = make_dummy_pdf("Company Alpha Proprietary Runbook")
    up_resp = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"file": ("alpha_runbook.pdf", pdf_stream, "application/pdf")}
    )
    assert up_resp.status_code == 201
    doc_a_id = up_resp.json()["document_id"]

    # User A lists documents: includes alpha_runbook
    list_a = client.get("/api/documents", headers={"Authorization": f"Bearer {token_a}"})
    assert list_a.status_code == 200
    docs_a = list_a.json()
    assert any(d["id"] == doc_a_id for d in docs_a)

    # User B lists documents: returns empty list
    list_b = client.get("/api/documents", headers={"Authorization": f"Bearer {token_b}"})
    assert list_b.status_code == 200
    docs_b = list_b.json()
    assert len(docs_b) == 0
    assert not any(d["id"] == doc_a_id for d in docs_b)


def test_user_b_delete_on_user_a_doc_returns_404():
    """User B's DELETE on A's document returns 404 (not 403) and doc still exists for A."""
    token_a = generate_test_token(USER_A_ID)
    token_b = generate_test_token(USER_B_ID)

    pdf_stream = make_dummy_pdf("Secret strategic planning document")
    up_resp = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"file": ("secret_plan.pdf", pdf_stream, "application/pdf")}
    )
    doc_id = up_resp.json()["document_id"]

    # User B attempts to DELETE User A's document
    del_resp = client.delete(
        f"/api/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    # Must return 404 to avoid document enumeration probing
    assert del_resp.status_code == 404

    # Document must still exist for User A
    list_a = client.get("/api/documents", headers={"Authorization": f"Bearer {token_a}"})
    assert any(d["id"] == doc_id for d in list_a.json())


# ============================================================================
# 5. RAG /ASK QUERY ISOLATION & CITATIONS
# ============================================================================

def test_user_b_ask_returns_none_of_user_a_content_or_citations():
    """
    User A has chunks indexed.
    User B queries /ask with an exact match of User A's content.
    Returns 0 citations and no chunks from User A.
    """
    token_a = generate_test_token(USER_A_ID)
    token_b = generate_test_token(USER_B_ID)

    # Directly insert test chunk belonging to User A
    chunk_a = DocumentChunk(
        chunk_id="chunk_alpha_001",
        document_id="doc_alpha_1",
        document_name="alpha_secret.pdf",
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=60,
        content_hash="hash_alpha_secret_1",
        embedding_model="text-embedding-3-small",
        section_heading="Top Secret Policy",
        text="The magic password for Project Pegasus is OMEGA-X-998877.",
        token_count=15,
        user_id=USER_A_ID
    )
    vector_store.add_document("doc_alpha_1", [chunk_a], user_id=USER_A_ID)
    corpus_bm25_index.update_index([chunk_a], user_id=USER_A_ID)

    # Mock LLM generation to test RAG pipeline response
    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="I do not have access to that information."))]
        )

        # User B queries with an exact match of User A's content
        resp_b = client.post(
            "/api/documents/ask",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"question": "The magic password for Project Pegasus is OMEGA-X-998877."}
        )
        assert resp_b.status_code == 200
        data_b = resp_b.json()

        # User B must receive NO citations or chunks from User A's document
        citations = data_b.get("citations", [])
        assert len(citations) == 0
        sources = data_b.get("sources", [])
        assert len(sources) == 0
        assert data_b.get("answerable") is False
        assert not any(c.get("chunk_id") == "chunk_alpha_001" for c in citations)


# ============================================================================
# 6. SAME FILE UPLOADED BY BOTH USERS CREATES INDEPENDENT DOCUMENTS
# ============================================================================

def test_same_file_uploaded_by_a_and_b_creates_two_independent_documents():
    """
    Uploading the identical byte stream by User A and User B produces two separate documents.
    Deleting User A's copy does not affect User B's copy.
    """
    token_a = generate_test_token(USER_A_ID)
    token_b = generate_test_token(USER_B_ID)

    pdf_bytes = make_dummy_pdf("Standard shared company compliance handbook 2026").getvalue()

    # User A uploads
    up_a = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"file": ("handbook.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    )
    assert up_a.status_code == 201
    doc_a_id = up_a.json()["document_id"]

    # User B uploads the exact same file
    up_b = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {token_b}"},
        files={"file": ("handbook.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    )
    assert up_b.status_code == 201
    doc_b_id = up_b.json()["document_id"]

    # Scoped IDs must be different
    assert doc_a_id != doc_b_id

    # User A deletes their copy
    del_a = client.delete(f"/api/documents/{doc_a_id}", headers={"Authorization": f"Bearer {token_a}"})
    assert del_a.status_code == 200

    # User B's copy still exists and is accessible
    status_b = client.get(f"/api/documents/{doc_b_id}/status", headers={"Authorization": f"Bearer {token_b}"})
    assert status_b.status_code == 200
    assert status_b.json()["document_id"] == doc_b_id


# ============================================================================
# 7. CLEAR ENDPOINT SCOPED TO CALLER ONLY
# ============================================================================

def test_clear_endpoint_only_clears_caller_documents():
    """User A calling /clear does not wipe User B's indexed documents."""
    token_a = generate_test_token(USER_A_ID)
    token_b = generate_test_token(USER_B_ID)

    chunk_a = DocumentChunk(
        chunk_id="chunk_a",
        document_id="doc_a",
        document_name="doc_a.pdf",
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=20,
        content_hash="hash_doc_a",
        embedding_model="text-embedding-3-small",
        section_heading="A",
        text="Text for User A",
        token_count=5,
        user_id=USER_A_ID
    )
    chunk_b = DocumentChunk(
        chunk_id="chunk_b",
        document_id="doc_b",
        document_name="doc_b.pdf",
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=20,
        content_hash="hash_doc_b",
        embedding_model="text-embedding-3-small",
        section_heading="B",
        text="Text for User B",
        token_count=5,
        user_id=USER_B_ID
    )

    vector_store.add_document("doc_a", [chunk_a], user_id=USER_A_ID)
    vector_store.add_document("doc_b", [chunk_b], user_id=USER_B_ID)

    # User A clears their documents
    clear_resp = client.delete("/api/documents/clear", headers={"Authorization": f"Bearer {token_a}"})
    assert clear_resp.status_code == 200

    # User A has 0 chunks
    assert len(vector_store.user_chunks_db.get(USER_A_ID, {})) == 0

    # User B still has their chunks intact
    assert len(vector_store.user_chunks_db.get(USER_B_ID, {})) == 1
    assert "chunk_b" in vector_store.user_chunks_db[USER_B_ID]


# ============================================================================
# 8. TOKEN WITH EMPTY SUB & AUTH_SECRET_KEY ENFORCEMENT
# ============================================================================

def test_token_with_missing_or_empty_sub_is_rejected():
    """Tokens with missing, empty, or whitespace-only 'sub' must return 401."""
    now = int(time.time())
    for bad_sub in ["", "   "]:
        payload = {
            "sub": bad_sub,
            "email": "test@example.com",
            "iat": now,
            "exp": now + 3600
        }
        token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
        resp = client.get("/api/documents", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401


def test_auth_secret_key_validation_fails_when_short_outside_test_mode(monkeypatch):
    """If AUTH_SECRET_KEY is unset or shorter than 32 chars, Settings must fail outside test mode."""
    from app.core.config import Settings
    import sys

    # Simulate running outside test mode
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.delenv("AUTH_SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with patch.dict(sys.modules, {"pytest": None}):
        # Short secret (< 32 characters)
        with pytest.raises(ValueError, match="at least 32 characters"):
            Settings(_env_file=None, AUTH_SECRET_KEY="too_short_key_under_32_chars")

        # Unset / empty secret
        with pytest.raises(ValueError, match="AUTH_SECRET_KEY is mandatory"):
            Settings(_env_file=None, AUTH_SECRET_KEY=None)


# ============================================================================
# 9. PERSISTENCE SOURCE OF TRUTH: REBUILD ON CACHE MISS
# ============================================================================

def test_persistence_source_of_truth_on_cache_miss():
    """
    Clearing all in-memory caches (user_document_store, user_chunks_db, corpus_bm25_index)
    must still enforce ownership, list documents, allow deletions, and answer queries
    by rebuilding state directly from Qdrant payloads.
    """
    token_a = generate_test_token(USER_A_ID)
    token_b = generate_test_token(USER_B_ID)

    # Seed User A document directly into Qdrant
    chunk_a = DocumentChunk(
        chunk_id="chunk_persist_001",
        document_id="doc_persist_a",
        document_name="architecture_spec.pdf",
        page_start=1,
        page_end=3,
        char_start=0,
        char_end=120,
        content_hash="hash_persist_a",
        embedding_model="text-embedding-3-small",
        section_heading="System Specs",
        text="The critical infrastructure threshold is set to 99.999% availability.",
        token_count=20,
        user_id=USER_A_ID
    )
    vector_store.add_document("doc_persist_a", [chunk_a], user_id=USER_A_ID)

    # Complete in-memory wipe: simulate fresh process or cache purge
    user_document_store.clear()
    vector_store.user_chunks_db.clear()
    vector_store.chunks_db.clear()
    corpus_bm25_index._user_corpora.clear()

    # 1. User A lists documents: rebuilt from Qdrant storage
    list_resp = client.get("/api/documents", headers={"Authorization": f"Bearer {token_a}"})
    assert list_resp.status_code == 200
    docs = list_resp.json()
    assert len(docs) == 1
    assert docs[0]["id"] == "doc_persist_a"
    assert docs[0]["name"] == "architecture_spec.pdf"

    # 2. User B tries to delete User A's document: Qdrant payload check returns 404
    user_document_store.clear()
    del_b = client.delete("/api/documents/doc_persist_a", headers={"Authorization": f"Bearer {token_b}"})
    assert del_b.status_code == 404

    # 3. User A deletes their document: succeeds
    del_a = client.delete("/api/documents/doc_persist_a", headers={"Authorization": f"Bearer {token_a}"})
    assert del_a.status_code == 200

    # 4. Confirmed deleted from Qdrant storage
    user_document_store.clear()
    list_a_after = client.get("/api/documents", headers={"Authorization": f"Bearer {token_a}"})
    assert list_a_after.status_code == 200
    assert len(list_a_after.json()) == 0


# ============================================================================
# 10. CHAT ISOLATION TESTS
# ============================================================================

def test_chat_isolation_user_b_cannot_list_read_or_delete_user_a_chats():
    """
    Chat conversations are strictly isolated:
    - User B cannot see User A's chats in list
    - User B cannot read User A's chat by ID (404)
    - User B cannot delete User A's chat (404)
    - User B clearing chats does not wipe User A's chats
    """
    token_a = generate_test_token(USER_A_ID)
    token_b = generate_test_token(USER_B_ID)

    # 1. User A creates a chat conversation
    chat_payload = {
        "title": "Confidential Security Audit Discussion",
        "messages": [
            {"role": "user", "text": "What are our vulnerability remediation SLAs?"},
            {"role": "assistant", "text": "Critical vulnerabilities must be patched within 24 hours."}
        ]
    }
    save_resp = client.post("/api/chats", headers={"Authorization": f"Bearer {token_a}"}, json=chat_payload)
    assert save_resp.status_code == 200
    chat_a_id = save_resp.json()["id"]

    # 2. User B lists chats: must be empty
    list_b = client.get("/api/chats", headers={"Authorization": f"Bearer {token_b}"})
    assert list_b.status_code == 200
    chats_b = list_b.json()
    assert not any(c["id"] == chat_a_id for c in chats_b)

    # 3. User B attempts to read User A's chat: 404
    get_b = client.get(f"/api/chats/{chat_a_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert get_b.status_code == 404

    # 4. User B attempts to delete User A's chat: 404
    del_b = client.delete(f"/api/chats/{chat_a_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert del_b.status_code == 404

    # 5. User A can still read their chat
    get_a = client.get(f"/api/chats/{chat_a_id}", headers={"Authorization": f"Bearer {token_a}"})
    assert get_a.status_code == 200
    assert get_a.json()["title"] == "Confidential Security Audit Discussion"

    # 6. User B clears their chats: User A's chat remains intact
    clear_b = client.post("/api/chats/clear", headers={"Authorization": f"Bearer {token_b}"})
    assert clear_b.status_code == 200

    list_a_after = client.get("/api/chats", headers={"Authorization": f"Bearer {token_a}"})
    assert list_a_after.status_code == 200
    assert any(c["id"] == chat_a_id for c in list_a_after.json())

    # Clean up test chat data
    from app.services.chat_history_service import chat_service
    chat_service.clear_user_chats(USER_A_ID)
    chat_service.clear_user_chats(USER_B_ID)


# ============================================================================
# 12. BM25 RETRIEVER FAILS CLOSED ON MISSING OR FOREIGN USER_ID
# ============================================================================

def test_hybrid_retriever_bm25_fails_closed_on_missing_or_other_user_id():
    """
    Test BM25 fail-closed user isolation:
    Adding one chunk for user A, one for user B, and one with user_id=None/""
    to the retriever, then searching as user A.
    Expect only A's chunk; the ownerless chunk and B's chunk must never be returned.
    """
    chunk_a = DocumentChunk(
        chunk_id="chunk_a_strict_bm25",
        document_id="doc_a_bm25",
        document_name="alpha_manual.pdf",
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=50,
        content_hash="hash_a_bm25",
        embedding_model="text-embedding-3-small",
        section_heading="Alpha Security",
        text="Kubernetes cluster security policy guidelines for User Alpha operational standards.",
        token_count=12,
        user_id=USER_A_ID
    )
    chunk_b = DocumentChunk(
        chunk_id="chunk_b_strict_bm25",
        document_id="doc_b_bm25",
        document_name="bravo_manual.pdf",
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=50,
        content_hash="hash_b_bm25",
        embedding_model="text-embedding-3-small",
        section_heading="Bravo Security",
        text="Kubernetes cluster security policy guidelines for User Bravo operational standards.",
        token_count=12,
        user_id=USER_B_ID
    )
    chunk_unowned = DocumentChunk(
        chunk_id="chunk_unowned_strict_bm25",
        document_id="doc_unowned_bm25",
        document_name="unowned_manual.pdf",
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=50,
        content_hash="hash_unowned_bm25",
        embedding_model="text-embedding-3-small",
        section_heading="Unowned Security",
        text="Kubernetes cluster security policy guidelines with no tenant owner attached.",
        token_count=12,
        user_id=""
    )

    # 1. Update index for user A passing mixed chunks (including B and ownerless)
    corpus_bm25_index.update_index([chunk_a, chunk_b, chunk_unowned], user_id=USER_A_ID)

    # 2. Update index for user B
    corpus_bm25_index.update_index([chunk_b], user_id=USER_B_ID)

    # 3. Search strictly as user A
    results = corpus_bm25_index.search(user_id=USER_A_ID, query="Kubernetes cluster security policy")

    result_cids = [c.chunk_id for c, _ in results]
    assert "chunk_a_strict_bm25" in result_cids
    assert "chunk_b_strict_bm25" not in result_cids
    assert "chunk_unowned_strict_bm25" not in result_cids
    assert len(results) == 1
    assert results[0][0].user_id == USER_A_ID


def test_bm25_cache_miss_rebuild_from_user_chunks_db(caplog):
    """
    Test BM25 cache-miss rebuild path:
    1. Populate vector_store.user_chunks_db with chunks for User A.
    2. Clear corpus_bm25_index._user_corpora to force a cache miss.
    3. Call corpus_bm25_index.search(user_id=USER_A_ID, query=...).
    4. Expect User A's chunks to be returned.
    5. Verify log does NOT report any skipped chunks (0 chunks skipped).
    """
    import logging
    chunk_a = DocumentChunk(
        chunk_id="chunk_a_cache_miss_001",
        document_id="doc_a_cm",
        document_name="alpha_architecture.pdf",
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=50,
        content_hash="hash_a_cm",
        embedding_model="text-embedding-3-small",
        section_heading="System Architecture",
        text="Kubernetes cluster control plane high availability configuration and telemetry.",
        token_count=12,
        user_id=USER_A_ID
    )

    # 1. Put chunk into vector_store.user_chunks_db
    vector_store.user_chunks_db.setdefault(USER_A_ID, {})[chunk_a.chunk_id] = chunk_a

    # 2. Clear corpus_bm25_index._user_corpora
    corpus_bm25_index._user_corpora.clear()
    assert USER_A_ID not in corpus_bm25_index._user_corpora

    # 3. Call search as User A under caplog to inspect warning logs
    with caplog.at_level(logging.WARNING):
        results = corpus_bm25_index.search(user_id=USER_A_ID, query="Kubernetes control plane high availability")

    # 4. Expect A's chunk back
    result_cids = [c.chunk_id for c, _ in results]
    assert "chunk_a_cache_miss_001" in result_cids
    assert len(results) == 1
    assert results[0][0].user_id == USER_A_ID

    # 5. Check logs: no skipped chunks warning should be emitted
    skipped_warnings = [rec.message for rec in caplog.records if "Skipped" in rec.message and "BM25 index" in rec.message]
    assert len(skipped_warnings) == 0, f"Expected 0 skipped chunk warnings, got: {skipped_warnings}"


def test_bm25_empty_valid_chunks_cleans_corpus_and_search_returns_empty():
    """
    Test when all chunks passed have user_id="":
    1. update_index(all_unowned_chunks, user_id=USER_A_ID) removes any existing
       entry from self._user_corpora[user_id] and returns early without building BM25.
    2. Calling search(user_id=USER_A_ID, ...) returns [] cleanly without raising any error.
    """
    unowned_1 = DocumentChunk(
        chunk_id="chunk_unowned_001",
        document_id="doc_unowned_1",
        document_name="unowned_doc.pdf",
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=50,
        content_hash="hash_u1",
        embedding_model="text-embedding-3-small",
        section_heading="General Info",
        text="Kubernetes operational clusters and deployment practices.",
        token_count=10,
        user_id=""
    )
    unowned_2 = DocumentChunk(
        chunk_id="chunk_unowned_002",
        document_id="doc_unowned_2",
        document_name="unowned_doc2.pdf",
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=50,
        content_hash="hash_u2",
        embedding_model="text-embedding-3-small",
        section_heading="General Info 2",
        text="Kubernetes networking policies and ingress controller setups.",
        token_count=10,
        user_id=""
    )

    # First, populate user A with a legitimate chunk so an entry exists in _user_corpora
    valid_a = DocumentChunk(
        chunk_id="chunk_a_initial",
        document_id="doc_a_initial",
        document_name="a.pdf",
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=40,
        content_hash="hash_ai",
        embedding_model="text-embedding-3-small",
        section_heading="Initial",
        text="Kubernetes cluster for User Alpha.",
        token_count=8,
        user_id=USER_A_ID
    )
    corpus_bm25_index.update_index([valid_a], user_id=USER_A_ID)
    assert USER_A_ID in corpus_bm25_index._user_corpora

    # Now call update_index where ALL chunks have user_id=""
    corpus_bm25_index.update_index([unowned_1, unowned_2], user_id=USER_A_ID)

    # Verify existing entry was removed
    assert USER_A_ID not in corpus_bm25_index._user_corpora

    # Ensure search(user_id=USER_A_ID, ...) returns [] without raising
    results = corpus_bm25_index.search(user_id=USER_A_ID, query="Kubernetes operational clusters")
    assert results == []


