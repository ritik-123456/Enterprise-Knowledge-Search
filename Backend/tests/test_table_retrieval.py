import pytest
from app.services.hybrid_retriever import tokenize_for_bm25, cross_encoder_reranker
from app.schemas.rag import DocumentChunk


def test_compound_entity_tokenization():
    sample_text = (
        "Table 2: The Transformer achieves better BLEU scores. "
        "Figure 1: The model architecture. "
        "See Section 5.4 for Regularization and Eq. 3 for attention."
    )
    tokens = tokenize_for_bm25(sample_text)

    # Verify compound tokens are properly extracted
    assert "table_2" in tokens
    assert "figure_1" in tokens
    assert "section_5.4" in tokens
    assert "equation_3" in tokens


def test_entity_rerank_boosting():
    c_table = DocumentChunk(
        chunk_id="chunk_table_2",
        document_id="doc1",
        document_name="Test.pdf",
        page_start=7,
        page_end=8,
        section_heading="5.4 Regularization",
        text="Table 2: The Transformer achieves better BLEU scores on newstest2014. ByteNet 23.75, GNMT 24.60.",
        token_count=50,
        content_hash="hash1",
        embedding_model="text-embedding-3-small",
        char_start=0,
        char_end=100
    )

    c_noise = DocumentChunk(
        chunk_id="chunk_noise",
        document_id="doc1",
        document_name="Test.pdf",
        page_start=2,
        page_end=2,
        section_heading="Background",
        text="There are 2 main approaches. We also show another table in the appendix.",
        token_count=50,
        content_hash="hash2",
        embedding_model="text-embedding-3-small",
        char_start=0,
        char_end=100
    )

    query = "What is in Table 2?"
    reranked = cross_encoder_reranker.rerank(query, [c_noise, c_table], top_n=2)

    # c_table MUST be ranked #1 with a significantly higher score due to compound entity boost
    assert reranked[0][0].chunk_id == "chunk_table_2"
    assert reranked[0][1] > reranked[1][1]


def test_strip_table_html_and_dummy_columns():
    from app.services.rag_service import strip_chunk_id_citations

    raw_table_output = (
        "| Col1 | Col2 | Col3 |\n"
        "|---|---|---|\n"
        "| base | 6<br>512<br>2048 | 4.92<br>25.8 [chunk_123_p9_c01] |\n"
        "| (A) | 1<br>512<br>512 | 5.29<br>24.9 |"
    )

    cleaned = strip_chunk_id_citations(raw_table_output)
    assert "<br>" not in cleaned
    assert "<br/>" not in cleaned
    assert "Col1" not in cleaned
    assert "Col2" not in cleaned
    assert "chunk_123_p9_c01" not in cleaned
    assert "6 512 2048" in cleaned

