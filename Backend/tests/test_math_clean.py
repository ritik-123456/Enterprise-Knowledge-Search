import pytest
from app.services.rag_service import clean_latex_delimiters, strip_chunk_id_citations


def test_clean_latex_delimiters():
    sample = (
        "It is composed of a stack of $N = 6$ identical layers.\n"
        "Outputs of dimension $d_{\\text{model}} = 512$.\n"
        "Continuous representations $\\mathbf{z} = (z_1, \\dots, z_n)$.\n"
        "$$\\text{Attention}(Q, K, V) = \\text{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V$$\n"
        "$$\\text{MultiHead}(Q, K, V) = \\text{Concat}(\\text{head}_1,\n"
    )

    cleaned = clean_latex_delimiters(sample)
    print("Cleaned text:\n", cleaned)

    assert "$N = 6$" not in cleaned
    assert "N = 6 identical layers" in cleaned
    assert "$d_{\\text{model}} = 512$" not in cleaned
    assert "d_model = 512" in cleaned
    assert "z = (z_1, ... , z_n)" in cleaned or "z = (z_1, ..., z_n)" in cleaned
    assert "$$" not in cleaned
    assert "$" not in cleaned


def test_strip_section_citations():
    text = (
        "We used the Adam optimizer with beta_1 = 0.9, beta_2 = 0.98, and epsilon = 10^-9 [5.3].\n"
        "Hardware details are in [Section 5.2].\n"
        "Model checkpoint [9445dbf864e9_p7_c015] was evaluated on test set."
    )
    cleaned = strip_chunk_id_citations(text)
    assert "[5.3]" not in cleaned
    assert "[Section 5.2]" not in cleaned
    assert "[9445dbf864e9_p7_c015]" not in cleaned
    assert "epsilon = 10^-9." in cleaned


def test_heading_detection_and_grounding():
    from app.services.chunking_service import detect_heading_line
    from app.services.rag_service import resolve_grounding_text

    # Verify bold markdown headings produced by PDF parser are correctly detected
    assert detect_heading_line("**5.3** **Optimizer**") == "5.3 Optimizer"
    assert detect_heading_line("**1 Introduction**") == "1 Introduction"
    assert detect_heading_line("## 5.3 Optimizer") == "5.3 Optimizer"

    # Verify oversized parent text windowing
    chunk = "[Document: test.pdf | Section: 5.3 Optimizer | Page 7]\nWe used the Adam optimizer with beta_1 = 0.9."
    bloated_parent = ("Prefix noise " * 500) + "We used the Adam optimizer with beta_1 = 0.9." + (" Suffix noise " * 500)
    windowed = resolve_grounding_text(chunk, bloated_parent, max_chars=1000)

    assert len(windowed) <= 1000
    assert "We used the Adam optimizer" in windowed

