import time
from unittest.mock import MagicMock, patch

import fitz
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.services.vector_store import vector_store


def create_test_pdf(text: str = "Acme Corp remote work policy allows employees up to three days remote per week.") -> bytes:
    """Creates a valid in-memory PDF document with readable text."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def client():
    """TestClient fixture with clean index state."""
    with TestClient(app) as test_client:
        test_client.delete("/api/documents/clear")
        yield test_client
        test_client.delete("/api/documents/clear")


def test_upload_then_poll_to_ready(client):
    """
    Test 1: Upload returns immediately with document_id and can be polled to ready.
    """
    pdf_bytes = create_test_pdf("Kubernetes cluster troubleshooting guide and node memory limits.")

    upload_resp = client.post(
        "/api/documents/upload",
        files={"file": ("cluster_guide.pdf", pdf_bytes, "application/pdf")}
    )
    assert upload_resp.status_code == 201
    upload_data = upload_resp.json()
    assert "document_id" in upload_data
    doc_id = upload_data["document_id"]
    assert upload_data["file_name"] == "cluster_guide.pdf"

    # Poll status until ready (or failed)
    max_wait = 5.0
    start = time.time()
    status_data = None

    while time.time() - start < max_wait:
        status_resp = client.get(f"/api/documents/{doc_id}/status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        if status_data["status"] in ("ready", "failed"):
            break
        time.sleep(0.1)

    assert status_data is not None
    assert status_data["status"] == "ready"
    assert status_data["page_count"] >= 1
    assert status_data["chunk_count"] >= 1
    assert status_data["reason"] is None


def test_list_documents(client):
    """
    Test 2: GET /api/documents returns registered documents with required metadata.
    """
    pdf_bytes = create_test_pdf("Human Resources employee handbook and code of conduct.")
    upload_resp = client.post(
        "/api/documents/upload",
        files={"file": ("hr_handbook.pdf", pdf_bytes, "application/pdf")}
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["document_id"]

    # Poll until ready
    for _ in range(50):
        s = client.get(f"/api/documents/{doc_id}/status").json()
        if s["status"] == "ready":
            break
        time.sleep(0.1)

    # List documents
    list_resp = client.get("/api/documents")
    assert list_resp.status_code == 200
    docs = list_resp.json()
    assert isinstance(docs, list)
    assert len(docs) >= 1

    doc_item = next((d for d in docs if d["id"] == doc_id), None)
    assert doc_item is not None
    assert doc_item["name"] == "hr_handbook.pdf"
    assert doc_item["page_count"] >= 1
    assert doc_item["chunk_count"] >= 1
    assert doc_item["status"] == "ready"


def test_ask_with_valid_citations(client):
    """
    Test 3: POST /api/documents/ask synthesizes answers with valid citations and measured response_time.
    """
    pdf_bytes = create_test_pdf("Health insurance dental and vision coverage begins on the first day of employment.")
    upload_resp = client.post(
        "/api/documents/upload",
        files={"file": ("benefits.pdf", pdf_bytes, "application/pdf")}
    )
    doc_id = upload_resp.json()["document_id"]

    for _ in range(50):
        if client.get(f"/api/documents/{doc_id}/status").json()["status"] == "ready":
            break
        time.sleep(0.1)

    # Mock OpenAI response
    mock_openai_text = "Health insurance dental coverage begins on the first day of employment [doc_id_placeholder]."

    # Find the actual chunk_id for this uploaded document
    actual_chunk = next(c for c in vector_store.chunks_db.values() if c.document_id == doc_id)
    actual_chunk_id = actual_chunk.chunk_id
    mock_openai_text = f"Health insurance and dental coverage starts immediately [{actual_chunk_id}]."

    q = "dental and vision coverage on first day of employment"
    query_vector = vector_store._generate_local_embedding(q)

    with patch.object(settings, "OPENAI_API_KEY", "mock-openai-key"):
        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock(message=MagicMock(content=mock_openai_text))]
            mock_client.chat.completions.create.return_value = mock_resp

            # Mock embeddings create to return dimension-matching query vector
            mock_emb = MagicMock()
            mock_emb.data = [MagicMock(embedding=query_vector)]
            mock_client.embeddings.create.return_value = mock_emb

            mock_openai_cls.return_value = mock_client

            ask_resp = client.post(
                "/api/documents/ask",
                json={"question": q}
            )
            assert ask_resp.status_code == 200
            data = ask_resp.json()

            assert data["answerable"] is True
            assert len(data["citations"]) >= 1
            first_citation = data["citations"][0]
            assert first_citation["chunk_id"] == actual_chunk_id
            assert first_citation["source_name"] == "benefits.pdf"

            # response_time must be measured real field
            assert "response_time" in data
            assert data["response_time"].endswith("s")

            # Embeddings must not leak in response
            assert "embedding" not in ask_resp.text


def test_unanswerable_question_returns_answerable_false(client):
    """
    Test 4: Unanswerable query returns answerable=False and zero citations.
    """
    pdf_bytes = create_test_pdf("Network topology and VPC peering routing tables for enterprise cloud clusters.")
    upload_resp = client.post(
        "/api/documents/upload",
        files={"file": ("vpc_peering.pdf", pdf_bytes, "application/pdf")}
    )
    doc_id = upload_resp.json()["document_id"]

    for _ in range(50):
        if client.get(f"/api/documents/{doc_id}/status").json()["status"] == "ready":
            break
        time.sleep(0.1)

    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [
            MagicMock(message=MagicMock(content="Information regarding this topic was not found in the uploaded documents."))
        ]
        mock_client.chat.completions.create.return_value = mock_resp
        mock_openai_cls.return_value = mock_client

        ask_resp = client.post(
            "/api/documents/ask",
            json={"question": "What is the corporate pet policy for office dogs?"}
        )
        assert ask_resp.status_code == 200
        data = ask_resp.json()
        assert data["answerable"] is False
        assert len(data["citations"]) == 0
        assert "not found" in data["answer"].lower()


def test_delete_then_ask(client):
    """
    Test 5: DELETE /api/documents/{document_id} deletes document; asking with deleted ID returns 404.
    """
    pdf_bytes = create_test_pdf("Confidential internal project roadmap and milestones.")
    upload_resp = client.post(
        "/api/documents/upload",
        files={"file": ("roadmap.pdf", pdf_bytes, "application/pdf")}
    )
    doc_id = upload_resp.json()["document_id"]

    for _ in range(50):
        if client.get(f"/api/documents/{doc_id}/status").json()["status"] == "ready":
            break
        time.sleep(0.1)

    # Delete the document
    del_resp = client.delete(f"/api/documents/{doc_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["document_id"] == doc_id

    # Verify deleted from listing
    list_docs = client.get("/api/documents").json()
    assert not any(d["id"] == doc_id for d in list_docs)

    # Asking specifically for this deleted document_id returns 404
    ask_resp = client.post(
        "/api/documents/ask",
        json={"question": "What are the roadmap milestones?", "document_id": doc_id}
    )
    assert ask_resp.status_code == 404


def test_oversized_file_returns_413(client):
    """
    Test 6: Files exceeding MAX_UPLOAD_MB return HTTP 413.
    """
    # Exceeds settings.MAX_UPLOAD_MB
    huge_bytes = b"%PDF-1.7\n" + (b"0" * (settings.MAX_UPLOAD_MB * 1024 * 1024 + 1024))
    resp = client.post(
        "/api/documents/upload",
        files={"file": ("huge_oversized.pdf", huge_bytes, "application/pdf")}
    )
    assert resp.status_code == 413
    assert "exceeds maximum allowed upload size" in resp.json()["detail"].lower()


def test_non_pdf_file_returns_400(client):
    """
    Test 7: Non-PDF files or files missing %PDF header return HTTP 400.
    """
    # 1. Non-pdf extension
    resp_ext = client.post(
        "/api/documents/upload",
        files={"file": ("notes.txt", b"Plain text notes", "text/plain")}
    )
    assert resp_ext.status_code == 400

    # 2. PDF extension but plain text content (missing %PDF header)
    resp_magic = client.post(
        "/api/documents/upload",
        files={"file": ("fake.pdf", b"This file is missing magic bytes", "application/pdf")}
    )
    assert resp_magic.status_code == 400


def test_unknown_document_id_returns_404(client):
    """
    Test 8: Unknown document IDs return HTTP 404 on status, delete, and ask endpoints.
    """
    fake_id = "0000000000000000000000000000000000000000000000000000000000000000"

    # Status 404
    resp_status = client.get(f"/api/documents/{fake_id}/status")
    assert resp_status.status_code == 404

    # Delete 404
    resp_del = client.delete(f"/api/documents/{fake_id}")
    assert resp_del.status_code == 404

    # Ask 404
    resp_ask = client.post(
        "/api/documents/ask",
        json={"question": "Test question", "document_id": fake_id}
    )
    assert resp_ask.status_code == 404


def test_ask_with_single_document_id_filter(client):
    """
    Test 9: Passing document_id restricts the search strictly to that document.
    """
    pdf_a = create_test_pdf("Document Alpha details server architecture and port 8080.")
    pdf_b = create_test_pdf("Document Beta details database clustering and replication.")

    id_a = client.post("/api/documents/upload", files={"file": ("doc_a.pdf", pdf_a, "application/pdf")}).json()["document_id"]
    id_b = client.post("/api/documents/upload", files={"file": ("doc_b.pdf", pdf_b, "application/pdf")}).json()["document_id"]

    for d_id in (id_a, id_b):
        for _ in range(50):
            if client.get(f"/api/documents/{d_id}/status").json()["status"] == "ready":
                break
            time.sleep(0.1)

    # Ask filtering specifically by document A
    resp = client.post(
        "/api/documents/ask",
        json={"question": "server architecture", "document_id": id_a}
    )
    assert resp.status_code == 200
    data = resp.json()
    if data["citations"]:
        for cit in data["citations"]:
            assert cit["source_name"] == "doc_a.pdf"
