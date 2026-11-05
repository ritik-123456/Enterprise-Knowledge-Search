import json
from unittest.mock import MagicMock, patch
import pytest
from fastapi.responses import StreamingResponse

from app.api.rag import ask_question
from app.schemas.rag import AskAIRequest
from app.services.rag_service import rag_service


def test_answer_query_stream_tokens_and_done():
    """Verify that rag_service.answer_query_stream emits token events and final done event."""
    mock_prep = {
        "client": MagicMock(),
        "create_kwargs": {"messages": [{"role": "user", "content": "What is the policy?"}]},
        "retrieved_map": {
            "chunk_1": MagicMock(
                chunk_id="chunk_1",
                document_name="Handbook.pdf",
                page_start=2,
                page_end=2,
                text="Employees are permitted up to 3 days remote."
            )
        },
        "retrieval_strength": "High"
    }

    tokens = ["Employees ", "are ", "allowed ", "to ", "work ", "remotely. [1]"]

    def mock_stream():
        for tok in tokens:
            choice = MagicMock()
            choice.delta = MagicMock(content=tok)
            chunk = MagicMock(choices=[choice])
            yield chunk

    mock_prep["client"].chat.completions.create.return_value = mock_stream()

    mock_citation = MagicMock(
        id=1,
        source_name="Handbook.pdf",
        page_display="Page 2",
        page_start=2,
        page_end=2,
        snippet="Employees are permitted up to 3 days remote.",
        model_dump=lambda: {
            "id": 1,
            "source_name": "Handbook.pdf",
            "page_display": "Page 2",
            "page_start": 2,
            "page_end": 2,
            "snippet": "Employees are permitted up to 3 days remote."
        }
    )

    with patch.object(rag_service, "_prepare_query_context_v2", return_value=(mock_prep, None)):
        with patch.object(rag_service, "_validate_citations", return_value=([mock_citation], False)):
            gen = rag_service.answer_query_stream(
                question="What is the policy?",
                user_id="test_user_stream_unit"
            )
            raw_events = list(gen)

    assert len(raw_events) == len(tokens) + 1

    parsed_events = [json.loads(e.replace("data: ", "").strip()) for e in raw_events]
    token_events = [e for e in parsed_events if e["type"] == "token"]
    done_events = [e for e in parsed_events if e["type"] == "done"]

    assert len(token_events) == len(tokens)
    assert "".join(e["token"] for e in token_events) == "".join(tokens)

    assert len(done_events) == 1
    done = done_events[0]
    assert done["answerable"] is True
    assert done["sources_used"] == 1
    assert done["confidence"] == "High"
    assert len(done["sources"]) == 1
    assert done["sources"][0]["source_name"] == "Handbook.pdf"


def test_ask_endpoint_stream_returns_streaming_response():
    """Verify that calling ask_question route with stream=True returns text/event-stream StreamingResponse."""
    dummy_stream = iter(['data: {"type": "token", "token": "Hello"}\n\n'])

    with patch("app.api.rag.rag_service.answer_query_stream", return_value=dummy_stream):
        req = AskAIRequest(question="What is remote policy?")
        res = ask_question(payload=req, stream=True, user_id="unit_user")

        assert isinstance(res, StreamingResponse)
        assert res.media_type == "text/event-stream"
        assert res.headers.get("Cache-Control") == "no-cache"
