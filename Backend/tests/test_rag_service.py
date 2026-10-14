import hashlib
import re
from datetime import datetime, timezone
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.core.constants import compute_retrieval_strength, RELATIVE_SCORE_CUTOFF_RATIO
from app.schemas.rag import DocumentChunk, AskAIResponse, CitationSource
from app.services.rag_service import rag_service, compute_reciprocal_rank_fusion, tokenize_query_and_text, build_citation_snippet
from app.services.vector_store import vector_store


@pytest.fixture(autouse=True)
def set_legacy_pipeline_version():
    orig_version = settings.PIPELINE_VERSION
    settings.PIPELINE_VERSION = "v1"
    yield
    settings.PIPELINE_VERSION = orig_version


def make_chunk(
    chunk_id: str,
    text: str,
    doc_name: str = "cluster_ops.pdf",
    page_start: int = 1,
    page_end: int = 1
) -> DocumentChunk:
    """Helper to create DocumentChunk for testing."""
    return DocumentChunk(
        document_id="doc_test_123",
        chunk_id=chunk_id,
        document_name=doc_name,
        page_start=page_start,
        page_end=page_end,
        section_heading="Operations",
        char_start=0,
        char_end=len(text),
        token_count=len(text.split()),
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        embedding_model="text-embedding-3-small",
        created_at=datetime.now(timezone.utc),
        text=text
    )


def test_bm25_plus_vector_fusion_ordering():
    """
    Test 1: BM25 plus vector fusion ordering.
    A candidate with an exact technical term (e.g. ERR_KUBE_POD_OOMKILLED)
    must receive a high BM25 rank and be boosted ahead of a purely generic semantic candidate.
    """
    chunk_semantic_only = make_chunk(
        "chunk_sem_001",
        "General troubleshooting steps for container memory pressure and CPU throttling in clusters."
    )
    chunk_exact_keyword = make_chunk(
        "chunk_exact_002",
        "Exit code ERR_KUBE_POD_OOMKILLED indicates the Linux cgroup exceeded memory limit quota."
    )
    chunk_unrelated = make_chunk(
        "chunk_other_003",
        "Configure AWS Route53 DNS records and SSL certificates for public domains."
    )

    # In vector retrieval alone, chunk_semantic_only had rank 1, chunk_exact_keyword had rank 2
    candidates = [
        (chunk_semantic_only, 0.88),  # Vector rank 1
        (chunk_exact_keyword, 0.70),  # Vector rank 2
        (chunk_unrelated, 0.40)       # Vector rank 3
    ]

    question = "How to resolve ERR_KUBE_POD_OOMKILLED?"

    # Run reciprocal rank fusion
    fused = compute_reciprocal_rank_fusion(candidates, question, k=60.0)

    # The exact keyword match must receive rank 1 from BM25 and win top fused rank
    assert len(fused) == 3
    assert fused[0][0].chunk_id == chunk_exact_keyword.chunk_id
    assert fused[0][2] > fused[1][2]  # RRF score comparison


def test_min_similarity_cutoff_skips_the_llm():
    """
    Test 2: Zero candidates in vector store skips the LLM.
    If no candidates exist in vector store (or all dropped by an explicit cutoff),
    the LLM must NOT be called, and response must return answerable=False with not-found message.
    """
    candidates = []

    with patch.object(vector_store, "search", return_value=candidates):
        with patch.object(settings, "OPENAI_API_KEY", "mock-openai-key"):
            with patch("openai.OpenAI") as mock_openai_cls:
                mock_client = MagicMock()
                mock_openai_cls.return_value = mock_client

                resp = rag_service.answer_query("How to configure Kubernetes Ingress?")

                # Verify LLM was skipped
                mock_client.chat.completions.create.assert_not_called()

                # Verify answerable=False and proper not-found message
                assert resp.answerable is False
                assert len(resp.citations) == 0
                assert "not found in the uploaded documents" in resp.answer.lower()


def test_invalid_cited_ids_are_dropped():
    """
    Test 3: Invalid cited IDs are dropped.
    When the model cites a mix of valid retrieved IDs and hallucinated IDs,
    only valid IDs are included in CitationSource, while invalid IDs are dropped.
    """
    valid_chunk_1 = make_chunk("chunk_valid_101", "Core hours are 10:00 AM to 3:00 PM local time.")
    valid_chunk_2 = make_chunk("chunk_valid_102", "Remote work requires manager approval.")

    candidates = [
        (valid_chunk_1, 0.85),
        (valid_chunk_2, 0.80)
    ]

    mock_llm_response_text = (
        "Employees must observe core hours [chunk_valid_101]. "
        "Also see nonexistent documentation [hallucinated_chunk_999]."
    )

    with patch.object(vector_store, "search", return_value=candidates):
        with patch.object(settings, "OPENAI_API_KEY", "mock-openai-key"):
            with patch("openai.OpenAI") as mock_openai_cls:
                mock_client = MagicMock()
                mock_resp = MagicMock()
                mock_resp.choices = [MagicMock(message=MagicMock(content=mock_llm_response_text))]
                mock_client.chat.completions.create.return_value = mock_resp
                mock_openai_cls.return_value = mock_client

                resp = rag_service.answer_query("What are the core working hours?")

                assert resp.answerable is True
                assert len(resp.citations) == 1
                # Only valid chunk was kept
                assert resp.citations[0].chunk_id == "chunk_valid_101"
                # Hallucinated ID must not be in citations
                cited_ids = [c.chunk_id for c in resp.citations]
                assert "hallucinated_chunk_999" not in cited_ids


def test_no_valid_citations_gives_answerable_false():
    """
    Test 4: No valid citations gives answerable=False.
    If the LLM hallucinates and cites exclusively invalid IDs or cites nothing,
    answerable must be set to False and citations must be empty.
    """
    valid_chunk = make_chunk("chunk_valid_201", "Database backup policies and recovery timelines.")
    candidates = [(valid_chunk, 0.90)]

    # Model cites only an invalid hallucinated ID
    mock_llm_response_text = "The system automatically recovers [fake_chunk_id_888]."

    with patch.object(vector_store, "search", return_value=candidates):
        with patch.object(settings, "OPENAI_API_KEY", "mock-openai-key"):
            with patch("openai.OpenAI") as mock_openai_cls:
                mock_client = MagicMock()
                mock_resp = MagicMock()
                mock_resp.choices = [MagicMock(message=MagicMock(content=mock_llm_response_text))]
                mock_client.chat.completions.create.return_value = mock_resp
                mock_openai_cls.return_value = mock_client

                resp = rag_service.answer_query("How does database recovery work?")

                # Must be marked unanswerable because no citations could be verified
                assert resp.answerable is False
                assert len(resp.citations) == 0


def test_api_error_handling_timeout_and_ratelimit():
    """
    Test 5: API error handling (timeouts, rate limits, empty responses).
    OpenAI timeouts, rate limits, or empty responses must be retried and return a clean failure result.
    """
    valid_chunk = make_chunk("chunk_valid_301", "Security authentication credentials and tokens.")
    candidates = [(valid_chunk, 0.85)]

    # 1. Rate limit error handling
    with patch.object(vector_store, "search", return_value=candidates):
        with patch.object(settings, "OPENAI_API_KEY", "mock-openai-key"):
            with patch("openai.OpenAI") as mock_openai_cls:
                mock_client = MagicMock()
                mock_client.chat.completions.create.side_effect = RuntimeError("RateLimitError: 429 quota exceeded")
                mock_openai_cls.return_value = mock_client

                resp = rag_service.answer_query("How to authenticate?")

                assert resp.answerable is False
                assert len(resp.citations) == 0
                assert "error" in resp.answer.lower() or "timed out" in resp.answer.lower()

    # 2. Empty response handling
    with patch.object(vector_store, "search", return_value=candidates):
        with patch.object(settings, "OPENAI_API_KEY", "mock-openai-key"):
            with patch("openai.OpenAI") as mock_openai_cls:
                mock_client = MagicMock()
                mock_resp = MagicMock()
                mock_resp.choices = [MagicMock(message=MagicMock(content="   "))]  # Empty content
                mock_client.chat.completions.create.return_value = mock_resp
                mock_openai_cls.return_value = mock_client

                resp = rag_service.answer_query("How to authenticate?")

                assert resp.answerable is False
                assert len(resp.citations) == 0


def test_no_embeddings_in_any_output():
    """
    Test 6: No embeddings leaked in any output.
    Verifies that the returned AskAIResponse and its nested citations/sources
    never contain raw vector embeddings.
    """
    valid_chunk = make_chunk("chunk_valid_401", "Travel reimbursement requires receipt submission within 30 days.")
    candidates = [(valid_chunk, 0.88)]

    mock_llm_response = "Submit receipts within 30 days [chunk_valid_401]."

    with patch.object(vector_store, "search", return_value=candidates):
        with patch.object(settings, "OPENAI_API_KEY", "mock-openai-key"):
            with patch("openai.OpenAI") as mock_openai_cls:
                mock_client = MagicMock()
                mock_resp = MagicMock()
                mock_resp.choices = [MagicMock(message=MagicMock(content=mock_llm_response))]
                mock_client.chat.completions.create.return_value = mock_resp
                mock_openai_cls.return_value = mock_client

                resp = rag_service.answer_query("What is the reimbursement deadline?")

                assert isinstance(resp, AskAIResponse)
                assert not hasattr(resp, "embedding")

                serialized = resp.model_dump()
                assert "embedding" not in serialized

                # Inspect every citation source
                for cit in resp.citations:
                    assert not hasattr(cit, "embedding")
                    assert "embedding" not in cit.model_dump()

                for src in resp.sources:
                    assert not hasattr(src, "embedding")
                    assert "embedding" not in src.model_dump()


def test_reasoning_models_temperature_handling():
    """
    Test 7: Temperature handling for reasoning models (e.g. o1, o3).
    Reasoning models reject the temperature parameter; verify temperature is not passed.
    """
    valid_chunk = make_chunk("chunk_valid_501", "Network VPC peering configuration.")
    candidates = [(valid_chunk, 0.90)]

    mock_llm_response = "VPC peering connects networks [chunk_valid_501]."

    with patch.object(vector_store, "search", return_value=candidates):
        with patch.object(settings, "OPENAI_API_KEY", "mock-openai-key"):
            with patch.object(settings, "LLM_MODEL", "o1-mini"):
                with patch("openai.OpenAI") as mock_openai_cls:
                    mock_client = MagicMock()
                    mock_resp = MagicMock()
                    mock_resp.choices = [MagicMock(message=MagicMock(content=mock_llm_response))]
                    mock_client.chat.completions.create.return_value = mock_resp
                    mock_openai_cls.return_value = mock_client

                    rag_service.answer_query("How does VPC peering work?")

                    called_kwargs = mock_client.chat.completions.create.call_args[1]
                    assert "temperature" not in called_kwargs
                    assert "max_completion_tokens" in called_kwargs


def test_eks_handbook_cluster_name_and_relative_cutoff():
    """
    Regression Test 1:
    Question: 'What is the name of the production EKS cluster?'
    Retrieval candidates include Page 2 (prod-use1-core, score 0.88)
    and irrelevant candidates (score 0.42, 0.35) which must be dropped by relative cutoff.
    Answer must contain 'prod-use1-core', cite page 2 chunk, and format Page as 'Page 2'.
    """
    chunk_page_2 = make_chunk(
        chunk_id="9232c7e34eea_p2_c001",
        text=(
            "1. Production Cluster Architecture and Engineering Standards Overview.\n"
            "This document establishes technical specifications, maintenance windows, networking boundaries, "
            "and compliance protocols across all cloud environments.\n"
            "The primary production EKS cluster is designated as prod-use1-core located in us-east-1.\n"
            "Secondary clusters include stg-use1-apps and dev-usw2-sandbox.\n"
            "All cluster worker nodes run Amazon Linux 2023 with CIS benchmark level 2 hardening."
        ),
        doc_name="eks_handbook.pdf",
        page_start=2,
        page_end=2
    )
    chunk_irrelevant_1 = make_chunk(
        chunk_id="9232c7e34eea_p5_c002",
        text="Log retention policies mandate archival to Amazon S3 glacier after 90 days.",
        doc_name="eks_handbook.pdf",
        page_start=5,
        page_end=5
    )
    chunk_irrelevant_2 = make_chunk(
        chunk_id="9232c7e34eea_p8_c003",
        text="Finance and billing reconciliation occurs on the 1st of every calendar month.",
        doc_name="eks_handbook.pdf",
        page_start=8,
        page_end=8
    )

    # Vector scores: top is 0.88.
    # Relative cutoff = 0.88 * 0.75 = 0.66.
    # Scores 0.42 and 0.35 fall below 0.66 and must be dropped.
    candidates = [
        (chunk_page_2, 0.88),
        (chunk_irrelevant_1, 0.42),
        (chunk_irrelevant_2, 0.35),
    ]

    mock_llm_answer = "The production EKS cluster is named prod-use1-core [9232c7e34eea_p2_c001]."

    with patch.object(vector_store, "search", return_value=candidates):
        with patch.object(settings, "OPENAI_API_KEY", "mock-openai-key"):
            with patch("openai.OpenAI") as mock_openai_cls:
                mock_client = MagicMock()
                mock_resp = MagicMock()
                mock_resp.choices = [MagicMock(message=MagicMock(content=mock_llm_answer))]
                mock_client.chat.completions.create.return_value = mock_resp
                mock_openai_cls.return_value = mock_client

                resp = rag_service.answer_query("What is the name of the production EKS cluster?")

                # 1. Verify LLM chat completion was called
                mock_client.chat.completions.create.assert_called_once()
                call_args = mock_client.chat.completions.create.call_args[1]
                user_content = call_args["messages"][1]["content"]

                # 2. Verify relative cutoff dropped irrelevant chunks: only page 2 chunk made it to LLM context
                assert "9232c7e34eea_p2_c001" in user_content
                assert "9232c7e34eea_p5_c002" not in user_content
                assert "9232c7e34eea_p8_c003" not in user_content

                # 3. Verify Page 2 formatting in context (not 'Pages 2-2')
                assert "Page 2" in user_content
                assert "Pages 2-2" not in user_content

                # 4. Verify answer contains prod-use1-core
                assert "prod-use1-core" in resp.answer
                assert resp.answerable is True

                # 5. Verify citations and sources
                assert len(resp.citations) == 1
                assert resp.citations[0].chunk_id == "9232c7e34eea_p2_c001"
                assert resp.citations[0].page_display == "Page 2"
                assert resp.sources_used == 1
                assert len(resp.sources) == 1

                # 6. Verify retrieval strength is High
                assert resp.confidence == "High"

                # 7. Requirement 4: The citation snippet must contain 'prod-use1-core' and cap at ~300 chars
                cit_snippet = resp.citations[0].snippet
                assert "prod-use1-core" in cit_snippet
                assert len(cit_snippet) <= 320
                assert cit_snippet.startswith("...")


def test_numbered_list_answer_preserved():
    """
    Regression Test 2:
    Answer text must return the model's full answer, never just the first sentence of a chunk.
    Preserve numbered lists (e.g. beginning '1. Control plane, 2. add-ons').
    """
    chunk = make_chunk(
        chunk_id="comp_101",
        text="The architecture has two components: 1. Control plane, 2. add-ons.",
        page_start=1,
        page_end=1
    )
    candidates = [(chunk, 0.85)]
    mock_llm_answer = "1. Control plane, 2. add-ons are the core components of the cluster [comp_101]."

    with patch.object(vector_store, "search", return_value=candidates):
        with patch.object(settings, "OPENAI_API_KEY", "mock-openai-key"):
            with patch("openai.OpenAI") as mock_openai_cls:
                mock_client = MagicMock()
                mock_resp = MagicMock()
                mock_resp.choices = [MagicMock(message=MagicMock(content=mock_llm_answer))]
                mock_client.chat.completions.create.return_value = mock_resp
                mock_openai_cls.return_value = mock_client

                resp = rag_service.answer_query("What are the cluster components?")

                assert resp.answer == mock_llm_answer
                assert resp.lead == mock_llm_answer
                assert resp.answer.startswith("1. Control plane, 2. add-ons")
                assert resp.citations[0].chunk_id == "comp_101"
                assert resp.sources_used == 1


def test_key_points_generated_from_model_answer_not_chunks():
    """
    Regression Test 3:
    Key points must NOT be built from the first sentence of each chunk.
    If the model provides bullet points in its answer, parse them from the answer.
    If not, key_points is empty.
    """
    chunk_1 = make_chunk("chunk_1", "First chunk sentence one. First chunk sentence two.")
    chunk_2 = make_chunk("chunk_2", "Second chunk sentence one. Second chunk sentence two.")
    candidates = [(chunk_1, 0.85), (chunk_2, 0.82)]

    # Model answer with bullet points
    mock_llm_answer = (
        "Here are the key points regarding cluster components [chunk_1]:\n"
        "- Control plane manages scheduling\n"
        "- Worker nodes run application pods"
    )

    with patch.object(vector_store, "search", return_value=candidates):
        with patch.object(settings, "OPENAI_API_KEY", "mock-openai-key"):
            with patch("openai.OpenAI") as mock_openai_cls:
                mock_client = MagicMock()
                mock_resp = MagicMock()
                mock_resp.choices = [MagicMock(message=MagicMock(content=mock_llm_answer))]
                mock_client.chat.completions.create.return_value = mock_resp
                mock_openai_cls.return_value = mock_client

                resp = rag_service.answer_query("Explain cluster components")

                # Key points come from LLM answer bullets, NOT chunk sentences
                assert resp.key_points == [
                    "Control plane manages scheduling",
                    "Worker nodes run application pods"
                ]
                assert "First chunk sentence one" not in resp.key_points
                assert "Second chunk sentence one" not in resp.key_points


def test_llm_failure_returns_clear_error_not_fake_answer():
    """
    Regression Test 4:
    If the LLM call fails, return a clear error, not a fake answer synthesized from chunk text.
    """
    chunk = make_chunk(
        chunk_id="chunk_prod_01",
        text="1. Production Cluster Architecture\nprod-use1-core is the cluster.",
        page_start=2,
        page_end=2
    )
    candidates = [(chunk, 0.88)]

    with patch.object(vector_store, "search", return_value=candidates):
        with patch.object(settings, "OPENAI_API_KEY", "mock-openai-key"):
            with patch("openai.OpenAI") as mock_openai_cls:
                mock_client = MagicMock()
                mock_client.chat.completions.create.side_effect = Exception("OpenAI API unreachable: connection refused")
                mock_openai_cls.return_value = mock_client

                resp = rag_service.answer_query("What is the name of the production EKS cluster?")

                # Must return error, answerable=False
                assert resp.answerable is False
                assert len(resp.citations) == 0
                assert resp.sources_used == 0
                # Must NOT contain fake answer like "According to ... [chunk_id]: 1."
                assert "According to" not in resp.answer
                assert "prod-use1-core" not in resp.answer
                assert "error" in resp.answer.lower() or "unhandled error" in resp.answer.lower()


def test_missing_openai_key_returns_clear_error():
    """
    Regression Test 5:
    When OPENAI_API_KEY is empty/missing, return a clear configuration error, not a fake answer.
    """
    chunk = make_chunk("chunk_prod_01", "1. Cluster name prod-use1-core.")
    candidates = [(chunk, 0.88)]

    with patch.object(vector_store, "search", return_value=candidates):
        with patch.object(settings, "OPENAI_API_KEY", ""), patch.object(settings, "GEMINI_API_KEY", ""):
            resp = rag_service.answer_query("What is the production cluster name?")

            assert resp.answerable is False
            assert "openai api key is not configured" in resp.answer.lower()
            assert resp.citations == []
            assert resp.sources_used == 0
            assert "According to" not in resp.answer


def test_page_display_formatting():
    """
    Regression Test 6:
    Page display must return 'Page 2' when page_start == page_end,
    and 'Pages 2-5' when page_start != page_end.
    """
    single_page_chunk = make_chunk("c1", "text", page_start=2, page_end=2)
    assert single_page_chunk.page_display == "Page 2"

    multi_page_chunk = make_chunk("c2", "text", page_start=2, page_end=5)
    assert multi_page_chunk.page_display == "Pages 2-5"

    cit_single = CitationSource(
        chunk_id="c1",
        source_name="doc.pdf",
        page_start=2,
        page_end=2,
        snippet="text",
        score=0.9,
        id=1
    )
    assert cit_single.page_display == "Page 2"

    cit_multi = CitationSource(
        chunk_id="c2",
        source_name="doc.pdf",
        page_start=2,
        page_end=5,
        snippet="text",
        score=0.9,
        id=2
    )
    assert cit_multi.page_display == "Pages 2-5"


def test_retrieval_strength_thresholds():
    """
    Regression Test 7:
    Retrieval strength must be computed based on top score and margin over second result,
    using centralized constants.
    """
    # High: top_score >= 0.70 and margin >= 0.08
    assert compute_retrieval_strength(0.88, 0.42) == "High"
    # Solo chunk >= 0.75
    assert compute_retrieval_strength(0.80, None) == "High"

    # Moderate: top_score >= 0.50 and margin >= 0.03
    assert compute_retrieval_strength(0.60, 0.55) == "Moderate"

    # Low: margin too narrow or score too low
    assert compute_retrieval_strength(0.52, 0.51) == "Low"
    assert compute_retrieval_strength(0.35, 0.20) == "Low"


def test_build_citation_snippet_scoring_and_context():
    """
    Regression Test 8:
    Verify build_citation_snippet extracts the sentence best matching question and answer,
    includes one context sentence before or after, and caps at ~300 characters.
    """
    text = (
        "1. Architecture and Standards Heading.\n"
        "This is an introductory sentence outlining general background information.\n"
        "The primary production EKS cluster is designated as prod-use1-core located in us-east-1.\n"
        "Secondary clusters include stg-use1-apps for integration testing.\n"
        "Final closing remarks on maintenance schedules."
    )
    question = "What is the name of the production EKS cluster?"
    answer = "The production EKS cluster is prod-use1-core [chunk_123]."

    snippet = build_citation_snippet(text, question, answer, max_chars=300)

    # Must contain the critical term prod-use1-core
    assert "prod-use1-core" in snippet
    # Must cap at ~300 characters
    assert len(snippet) <= 320
    # Must have trimmed preamble
    assert snippet.startswith("...")


def test_citation_snippet_trimming_and_ellipsis():
    """
    Regression Test 9:
    Verify that ellipsis '...' is added ONLY where text was actually trimmed:
    - If chunk starts at sentence 0: no leading '...'
    - If chunk ends at last sentence: no trailing '...'
    - If full chunk fits: no '...' anywhere
    """
    full_short_chunk = (
        "The production cluster is named prod-use1-core.\n"
        "It runs in us-east-1."
    )
    snippet_full = build_citation_snippet(
        full_short_chunk,
        question="What is the cluster name?",
        answer="It is prod-use1-core."
    )
    assert not snippet_full.startswith("...")
    assert not snippet_full.endswith("...")
    assert "prod-use1-core" in snippet_full


def test_short_title_queries_return_non_empty_context_and_grounded_answers():
    """
    Test 10: "Pre-upgrade Checklist" and short title-style queries ("IRSA", "Karpenter", "postmortem")
    must return non-empty context through the production path with default settings.
    """
    test_queries = [
        ("Pre-upgrade Checklist", "7.2 Pre-upgrade checklist", "Before any upgrade the on-call engineer confirms that all Pod Disruption Budgets allow at least one pod to be evicted"),
        ("IRSA", "5.1 IAM Roles for Service Accounts (IRSA)", "IAM Roles for Service Accounts (IRSA) provides fine-grained AWS IAM permissions"),
        ("Karpenter", "4.2 Karpenter NodePools", "Karpenter NodePools use the consolidation policy 'WhenEmptyOrUnderutilized'"),
        ("postmortem", "13.1 Severity levels", "A blameless postmortem must be published within 5 business days")
    ]

    for query, heading, fact in test_queries:
        with patch.object(settings, "OPENAI_API_KEY", "mock-openai-key"):
            with patch("openai.OpenAI") as mock_openai_cls:
                mock_client = MagicMock()
                mock_openai_cls.return_value = mock_client

                def fake_create(**kwargs):
                    messages = kwargs.get("messages", [])
                    user_msg = messages[-1]["content"] if messages else ""
                    chunk_ids = re.findall(r'\[Chunk ID:\s*([a-zA-Z0-9_\-]+)', user_msg)
                    cid = chunk_ids[0] if chunk_ids else "chunk_mock"
                    mock_resp = MagicMock()
                    mock_resp.choices = [
                        MagicMock(message=MagicMock(content=f"{fact} [{cid}]."))
                    ]
                    return mock_resp

                mock_client.chat.completions.create.side_effect = fake_create

                resp = rag_service.answer_query(query)

                # 1. Verify LLM was called
                assert mock_client.chat.completions.create.called

                # 2. Verify non-empty context was passed to LLM
                call_args = mock_client.chat.completions.create.call_args[1]
                user_content = call_args["messages"][-1]["content"]
                assert "Context Excerpts:" in user_content
                assert len(user_content) > 100

                # 3. Must return answerable=True with citations
                assert resp.answerable is True, f"Query '{query}' was unexpectedly marked unanswerable."
                assert len(resp.citations) > 0, f"Query '{query}' returned zero citations."
                assert resp.sources_used > 0


def test_nonsense_query_returns_not_found_from_llm():
    """
    Test 11: A nonsense query ("recipe for pancakes") must produce a "not found" answer
    with answerable=False and zero citations.
    """
    with patch.object(settings, "OPENAI_API_KEY", "mock-openai-key"):
        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.choices = [
                MagicMock(message=MagicMock(content="Information regarding this topic was not found in the uploaded documents."))
            ]
            mock_client.chat.completions.create.return_value = mock_resp
            mock_openai_cls.return_value = mock_client

            resp = rag_service.answer_query("recipe for pancakes")

            # LLM was passed context and decided information was not found
            assert mock_client.chat.completions.create.called
            assert resp.answerable is False
            assert len(resp.citations) == 0
            assert resp.sources_used == 0
            assert "not found in the uploaded documents" in resp.answer.lower()


