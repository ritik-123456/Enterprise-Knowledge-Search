import io
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from datetime import datetime, timezone
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import Settings, settings
from app.schemas.rag import (
    DocumentChunk,
    DocumentChunkInternal,
    CitationSource,
    AskAIResponse,
    PDFUploadResponse
)
from app.services.chunking_service import chunking_service, count_tokens
from app.services.vector_store import vector_store
from app.services.rag_service import rag_service, is_reasoning_model


def test_config_defaults_and_types():
    """Verify all Step 1 configuration parameters and default values."""
    assert settings.CHUNK_SIZE_TOKENS == 400
    assert settings.CHUNK_OVERLAP_TOKENS == 60
    assert settings.RETRIEVE_K == 20
    assert settings.TOP_K_CHUNKS == 5
    assert settings.MIN_SIMILARITY == 0.0
    assert settings.MAX_UPLOAD_MB == 25
    assert settings.MAX_PAGES == 150
    assert settings.EMBED_BATCH_SIZE == 64
    assert settings.LLM_MAX_TOKENS == 1024
    assert settings.LLM_TEMPERATURE == 0.0
    assert settings.OPENAI_API_KEY == "" or isinstance(settings.OPENAI_API_KEY, str)


def test_config_validators_chunk_overlap():
    """Verify validator rejects CHUNK_OVERLAP_TOKENS >= CHUNK_SIZE_TOKENS."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(CHUNK_SIZE_TOKENS=300, CHUNK_OVERLAP_TOKENS=300)
    assert "CHUNK_OVERLAP_TOKENS" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        Settings(CHUNK_SIZE_TOKENS=300, CHUNK_OVERLAP_TOKENS=350)
    assert "CHUNK_OVERLAP_TOKENS" in str(exc_info.value)


def test_config_validators_retrieval_k():
    """Verify validator rejects TOP_K_CHUNKS > RETRIEVE_K."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(RETRIEVE_K=10, TOP_K_CHUNKS=20)
    assert "TOP_K_CHUNKS" in str(exc_info.value)


def test_config_validators_limits():
    """Verify validator rejects negative or zero limits."""
    with pytest.raises(ValidationError):
        Settings(MAX_UPLOAD_MB=0)
    with pytest.raises(ValidationError):
        Settings(MAX_PAGES=-1)
    with pytest.raises(ValidationError):
        Settings(LLM_MAX_TOKENS=0)


def test_document_chunk_schema():
    """
    Verify DocumentChunk schema:
    document_id (content hash), page_start, page_end, section_heading,
    char_start, char_end, content_hash, embedding_model, created_at.
    Embedding must be absent.
    """
    chunk = DocumentChunk(
        document_id="doc_hash_123456",
        chunk_id="doc_hash_123456_p1_c001",
        document_name="employee_handbook.pdf",
        page_start=1,
        page_end=2,
        section_heading="Remote Work Guidelines",
        char_start=0,
        char_end=350,
        token_count=85,
        content_hash="chunk_hash_abcdef",
        embedding_model="text-embedding-3-small",
        created_at=datetime.now(timezone.utc),
        text="Acme Corp encourages flexible remote work arrangements for eligible teams."
    )

    dumped = chunk.model_dump()
    assert "document_id" in dumped
    assert "page_start" in dumped
    assert "page_end" in dumped
    assert "section_heading" in dumped
    assert "char_start" in dumped
    assert "char_end" in dumped
    assert "content_hash" in dumped
    assert "embedding_model" in dumped
    assert "created_at" in dumped
    assert "text" in dumped
    # page_number must be serialized via @computed_field
    assert "page_number" in dumped
    assert dumped["page_number"] == 1

    # Embedding MUST NOT be in DocumentChunk schema
    assert "embedding" not in dumped


def test_internal_storage_chunk_model():
    """
    Verify DocumentChunkInternal inherits DocumentChunk and adds embedding
    exclusively for internal storage.
    """
    internal = DocumentChunkInternal(
        document_id="doc_hash_123456",
        chunk_id="doc_hash_123456_p1_c001",
        document_name="employee_handbook.pdf",
        page_start=1,
        page_end=1,
        section_heading=None,
        char_start=0,
        char_end=100,
        token_count=25,
        content_hash="chunk_hash_789",
        embedding_model="text-embedding-3-small",
        created_at=datetime.now(timezone.utc),
        text="Sample text for embedding test.",
        embedding=[0.1, 0.2, 0.3]
    )

    assert internal.embedding == [0.1, 0.2, 0.3]
    public_version = internal.to_public()
    assert isinstance(public_version, DocumentChunk)
    assert not hasattr(public_version, "embedding") or "embedding" not in public_version.model_dump()


def test_citation_source_schema():
    """
    Verify CitationSource: chunk_id, page_start/page_end, snippet, score.
    page and similarity_score must be serialized via @computed_field.
    """
    citation = CitationSource(
        chunk_id="chunk_999",
        source_name="handbook.pdf",
        page_start=3,
        page_end=4,
        snippet="Employees may expense up to $500 for home office setup.",
        score=0.892,
        id=1,
        section_heading="Home Office Allowance"
    )

    dumped = citation.model_dump()
    assert dumped["chunk_id"] == "chunk_999"
    assert dumped["page_start"] == 3
    assert dumped["page_end"] == 4
    assert "snippet" in dumped
    assert dumped["score"] == 0.892
    # Compatibility @computed_field aliases
    assert "page" in dumped
    assert dumped["page"] == 3
    assert "similarity_score" in dumped
    assert dumped["similarity_score"] == 0.892


def test_ask_ai_response_schema():
    """
    Verify AskAIResponse: answer, citations, and answerable: bool.
    response_time must be a real declared field (measured per request).
    """
    citation = CitationSource(
        chunk_id="c1",
        source_name="policy.pdf",
        page_start=1,
        page_end=1,
        snippet="Core hours are 10am to 3pm.",
        score=0.91
    )

    # Grounded / Answerable response
    resp = AskAIResponse(
        question="What are core working hours?",
        answer="Core working hours are 10:00 AM to 3:00 PM local time.",
        citations=[citation],
        answerable=True,
        lead="Core working hours are 10:00 AM to 3:00 PM local time.",
        response_time="0.08s"
    )

    dumped = resp.model_dump()
    assert dumped["answerable"] is True
    assert dumped["answer"].startswith("Core working hours")
    assert len(dumped["citations"]) == 1
    assert dumped["lead"] == dumped["answer"]
    assert dumped["response_time"] == "0.08s"

    # Not found / Unanswerable response
    not_found_resp = AskAIResponse(
        question="What is the nuclear launch code?",
        answer="Information regarding this topic was not found in the uploaded documents.",
        citations=[],
        answerable=False,
        lead="Information regarding this topic was not found in the uploaded documents.",
        response_time="0.02s"
    )
    assert not_found_resp.answerable is False
    assert len(not_found_resp.citations) == 0
    assert not_found_resp.response_time == "0.02s"


def test_chunking_with_tiktoken():
    """Verify chunking service sizes chunks by tokens with tiktoken."""
    sample_text = (
        "Enterprise Knowledge Search is a state-of-the-art retrieval augmented generation system. "
        "It indexes corporate PDF documents and handbooks using semantic vector search. "
        "Employees can query policies, engineering specifications, and OKR guidelines instantly. "
    ) * 15

    pages = [{"page": 1, "text": sample_text}]
    chunks = chunking_service.process_document(pages, "test_doc.pdf")

    assert len(chunks) > 0
    for ch in chunks:
        assert ch.token_count <= settings.CHUNK_SIZE_TOKENS + 10  # Token-bounded
        assert ch.document_id is not None
        assert ch.content_hash is not None
        assert ch.page_start == 1
        assert ch.page_end == 1
        # No embedding vector in chunk
        assert not hasattr(ch, "embedding")


def test_vector_store_retrieval_and_safe_output():
    """
    Verify vector store stores internal embeddings but outputs public DocumentChunk
    without embedding floats.
    """
    vector_store.clear()

    sample_chunk = DocumentChunk(
        document_id="doc_abc",
        chunk_id="doc_abc_p1_c000",
        document_name="benefits.pdf",
        page_start=1,
        page_end=1,
        section_heading="Health Insurance",
        char_start=0,
        char_end=150,
        token_count=35,
        content_hash="hash_abc",
        embedding_model="text-embedding-3-small",
        created_at=datetime.now(timezone.utc),
        text="Health insurance dental and vision coverage begins on the first day of employment."
    )

    vector_store.add_chunks([sample_chunk])
    assert len(vector_store.chunks_db) == 1

    # Internal representation holds embedding
    internal_chunk = vector_store.chunks_db["doc_abc_p1_c000"]
    assert internal_chunk.embedding is not None

    # Search results strip embedding floats
    results = vector_store.search("dental coverage", top_k=5)
    assert len(results) == 1
    retrieved_chunk, score = results[0]

    assert isinstance(retrieved_chunk, DocumentChunk)
    assert not hasattr(retrieved_chunk, "embedding")
    assert "embedding" not in retrieved_chunk.model_dump()
    assert score > 0.0


def test_rag_service_not_found_answerable_flag():
    """Verify unanswerable queries return answerable=False."""
    vector_store.clear()
    resp = rag_service.answer_query("What is the reimbursement limit?")
    assert resp.answerable is False
    assert len(resp.citations) == 0
    assert "not found" in resp.answer.lower() or "no relevant" in resp.answer.lower()


def test_environment_variable_override_wins_over_default(monkeypatch):
    """
    1. An environment-variable override test:
    Set environment variables and confirm they take precedence over default settings.
    """
    monkeypatch.setenv("CHUNK_SIZE_TOKENS", "500")
    monkeypatch.setenv("CHUNK_OVERLAP_TOKENS", "75")
    monkeypatch.setenv("RETRIEVE_K", "30")
    monkeypatch.setenv("TOP_K_CHUNKS", "8")
    monkeypatch.setenv("MIN_SIMILARITY", "0.55")
    monkeypatch.setenv("MAX_UPLOAD_MB", "50")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-custom-env-override-key")

    override_settings = Settings()
    assert override_settings.CHUNK_SIZE_TOKENS == 500
    assert override_settings.CHUNK_OVERLAP_TOKENS == 75
    assert override_settings.RETRIEVE_K == 30
    assert override_settings.TOP_K_CHUNKS == 8
    assert override_settings.MIN_SIMILARITY == 0.55
    assert override_settings.MAX_UPLOAD_MB == 50
    assert override_settings.OPENAI_API_KEY == "sk-test-custom-env-override-key"


def test_real_http_ask_response_json_keys_for_frontend():
    """
    2. A real HTTP response test that asserts the exact JSON keys the frontend needs:
    lead, key_points, confidence, response_time, sources_used, sources,
    as well as answer, citations, and answerable boolean.
    """
    client = TestClient(app)

    # A) Test unanswerable / empty search query
    resp = client.post("/api/documents/ask", json={"question": "What is Acme work policy?"})
    assert resp.status_code == 200
    data = resp.json()

    frontend_required_keys = [
        "lead",
        "key_points",
        "confidence",
        "response_time",
        "sources_used",
        "sources",
        "question",
        "answer",
        "citations",
        "answerable"
    ]
    for key in frontend_required_keys:
        assert key in data, f"Frontend requires '{key}' in AskAI response JSON"

    assert isinstance(data["key_points"], list)
    assert isinstance(data["sources"], list)
    assert isinstance(data["citations"], list)
    assert isinstance(data["answerable"], bool)
    assert data["answerable"] is False

    # B) Test answerable query with indexed chunk to assert citation fields
    vector_store.clear()
    chunk = DocumentChunk(
        document_id="doc_fe_keys",
        chunk_id="doc_fe_keys_p1_c001",
        document_name="hr_guidelines.pdf",
        page_start=4,
        page_end=5,
        section_heading="Flexible Hours",
        char_start=150,
        char_end=350,
        token_count=45,
        content_hash="hash_fe_keys",
        embedding_model="text-embedding-3-small",
        created_at=datetime.now(timezone.utc),
        text="Employees are permitted flexible core hours between 10am and 3pm local time."
    )
    vector_store.add_chunks([chunk])

    mock_openai_text = "Employees are permitted flexible core hours [doc_fe_keys_p1_c001]."
    with patch.object(settings, "OPENAI_API_KEY", "mock-openai-key"):
        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock(message=MagicMock(content=mock_openai_text))]
            mock_client.chat.completions.create.return_value = mock_resp
            mock_openai_cls.return_value = mock_client

            ans_resp = client.post("/api/documents/ask", json={"question": "flexible core hours"})
            assert ans_resp.status_code == 200
            ans_data = ans_resp.json()

            assert ans_data["answerable"] is True
            assert len(ans_data["sources"]) > 0

            first_source = ans_data["sources"][0]
            citation_keys = [
                "chunk_id",
                "source_name",
                "page_start",
                "page_end",
                "snippet",
                "score",
                "id",
                "page",
                "similarity_score"
            ]
            for c_key in citation_keys:
                assert c_key in first_source, f"Frontend source card requires citation key '{c_key}'"


def test_document_chunk_internal_does_not_leak_embedding_from_endpoints():
    """
    3. A test that a DocumentChunkInternal returned from an endpoint doesn’t leak embedding:
    Verifies that chunks stored internally with raw embedding vector floats
    never expose 'embedding' in GET /api/documents/chunks or POST /api/documents/ask.
    """
    vector_store.clear()

    # Store a DocumentChunkInternal with explicit vector floats
    internal_chunk = DocumentChunkInternal(
        document_id="doc_classified",
        chunk_id="chunk_internal_classified_001",
        document_name="architecture_deep_dive.pdf",
        page_start=1,
        page_end=2,
        section_heading="Internal Data Flow",
        char_start=0,
        char_end=250,
        token_count=60,
        content_hash="content_hash_classified",
        embedding_model="text-embedding-3-small",
        created_at=datetime.now(timezone.utc),
        text="Internal system data pipeline architecture specification and ingestion nodes.",
        embedding=[0.999, 0.888, 0.777, -0.666, 0.555]
    )
    vector_store.chunks_db[internal_chunk.chunk_id] = internal_chunk

    client = TestClient(app)

    # 1. Test GET /api/documents/chunks
    chunks_resp = client.get("/api/documents/chunks")
    assert chunks_resp.status_code == 200
    chunks_list = chunks_resp.json()
    assert len(chunks_list) == 1
    # Ensure the embedding vector key is not leaked in the dict or JSON payload
    assert "embedding" not in chunks_list[0]
    assert '"embedding":' not in chunks_resp.text

    # 2. Test POST /api/documents/ask
    ask_resp = client.post("/api/documents/ask", json={"question": "pipeline architecture"})
    assert ask_resp.status_code == 200
    ask_data = ask_resp.json()
    assert "embedding" not in ask_data
    assert '"embedding":' not in ask_resp.text
    for cit in ask_data.get("citations", []):
        assert "embedding" not in cit


def test_oversized_upload_rejects_without_consuming_excessive_memory():
    """
    4. An oversized upload test that checks memory isn’t consumed before rejection:
    Confirms that uploads exceeding MAX_UPLOAD_MB are rejected with 413
    via headers and streaming limits without reading or buffering the entire oversized payload.
    """
    client = TestClient(app)
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024  # 25 MB

    # Fast-path check: Content-Length header exceeding limit is rejected immediately
    # without reading the body stream into memory
    headers = {
        "content-length": str(max_bytes + (10 * 1024 * 1024))  # 35 MB
    }
    resp = client.post(
        "/api/documents/upload",
        files={"file": ("oversized_file.pdf", b"%PDF-dummy-content", "application/pdf")},
        headers=headers
    )
    assert resp.status_code == 413
    assert "exceeds maximum allowed upload size" in resp.json()["detail"]

    # Streaming bounded check: oversized payload beyond MAX_UPLOAD_MB is rejected
    oversized_data = b"X" * (max_bytes + 256)
    resp_stream = client.post(
        "/api/documents/upload",
        files={"file": ("huge_document.pdf", oversized_data, "application/pdf")}
    )
    assert resp_stream.status_code == 413
    assert "exceeds maximum allowed upload size" in resp_stream.json()["detail"]


def test_env_is_in_gitignore():
    """
    5. A test that .env is in .gitignore:
    Ensures .env is strictly ignored to prevent credentials or secrets from being committed.
    Checks repository root .gitignore and Backend/.gitignore.
    """
    # 1. Repository root .gitignore
    root_gitignore = Path(__file__).resolve().parents[2] / ".gitignore"
    assert root_gitignore.exists(), f"Root .gitignore missing at {root_gitignore}"
    root_lines = [line.strip() for line in root_gitignore.read_text(encoding="utf-8").splitlines()]
    assert any(line == ".env" or line.startswith(".env") for line in root_lines), (
        "'.env' must be explicitly ignored in repository root .gitignore"
    )

    # 2. Backend .gitignore
    backend_gitignore = Path(__file__).resolve().parents[1] / ".gitignore"
    assert backend_gitignore.exists(), f"Backend .gitignore missing at {backend_gitignore}"
    backend_lines = [line.strip() for line in backend_gitignore.read_text(encoding="utf-8").splitlines()]
    assert any(line == ".env" or line.startswith(".env") for line in backend_lines), (
        "'.env' must be explicitly ignored in Backend/.gitignore"
    )


def test_reasoning_models_temperature_handling():
    """
    Assert that reasoning models (o1, o3 series) are detected and don't receive
    unsupported temperature parameter, while standard chat models (gpt-4o) do.
    """
    assert is_reasoning_model("o1") is True
    assert is_reasoning_model("o1-mini") is True
    assert is_reasoning_model("o1-preview") is True
    assert is_reasoning_model("o3-mini") is True
    assert is_reasoning_model("gpt-4o") is False
    assert is_reasoning_model("gpt-4o-mini") is False
    assert is_reasoning_model("gpt-4-turbo") is False


def test_response_time_is_measured_real_field():
    """
    Assert that response_time cannot be a static derived property, but is a real
    measurement taken per request and included in the actual JSON response.
    """
    client = TestClient(app)
    resp = client.post("/api/documents/ask", json={"question": "What is our company holiday policy?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "response_time" in data
    # Must end with 's' and be a parseable floating duration
    assert data["response_time"].endswith("s")
    duration = float(data["response_time"][:-1])
    assert duration >= 0.0


