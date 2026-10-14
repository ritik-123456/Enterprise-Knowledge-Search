import io
import pytest
import pymupdf
from fastapi.testclient import TestClient

from app.main import app
from app.services.pdf_service import (
    pdf_service,
    PDFValidationError,
    PDFOversizedError,
    PDFEncryptedError,
    PDFPageLimitError,
    PDFCorruptError,
)
from app.schemas.rag import PDFPageRecord, PDFHeading


def create_in_memory_pdf(pages_text: list[str], title: str = "Test Doc") -> bytes:
    """Helper to generate in-memory PDF bytes with text."""
    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page()
        page.insert_text((50, 72), text, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_hyphen_rules():
    """
    1. Hyphen rules:
    - Rejoin 'config-\nuration' -> 'configuration' (next line starts with lowercase).
    - Don't touch real hyphens like 'kube-\nsystem' -> 'kube-system'.
    - Don't touch hyphens followed by an uppercase letter or digit:
      'COVID-\n19', 'UTF-\n8', 'Kube-\nSystem'.
    """
    # Broken word with lowercase continuation -> rejoined into single word
    sample1 = "Please review the system config-\nuration settings before deploy."
    fixed1 = pdf_service.fix_hyphenation(sample1)
    assert "configuration" in fixed1
    assert "config-\nuration" not in fixed1

    # Real compound word 'kube-system' -> hyphen preserved
    sample2 = "Pod scheduled in the kube-\nsystem namespace."
    fixed2 = pdf_service.fix_hyphenation(sample2)
    assert "kube-system" in fixed2
    assert "kubesystem" not in fixed2

    # Followed by digit -> hyphen preserved, not rejoined
    sample3 = "Standard encoding is UTF-\n8 across all services."
    fixed3 = pdf_service.fix_hyphenation(sample3)
    assert "UTF-\n8" in fixed3

    sample4 = "Protocols for COVID-\n19 response."
    fixed4 = pdf_service.fix_hyphenation(sample4)
    assert "COVID-\n19" in fixed4

    # Followed by uppercase letter -> hyphen preserved, not rejoined
    sample5 = "Enterprise Multi-\nCloud architecture design."
    fixed5 = pdf_service.fix_hyphenation(sample5)
    assert "Multi-\nCloud" in fixed5


def test_header_footer_removal_multi_page():
    """
    2. Header/Footer removal:
    - Remove lines that repeat on more than 60% of pages (compared after stripping digits).
    - Skip this for documents under 5 pages.
    """
    page_bodies = [
        "Introduction to corporate policies and core values.",
        "Travel guidelines and expense reimbursement procedures.",
        "Remote work arrangements and core collaboration hours.",
        "Information security protocols and credential policies.",
        "Health insurance plans and comprehensive dental coverage.",
        "Annual performance reviews and quarterly OKR milestones."
    ]
    six_pages = [
        f"Acme Corp Confidential Policy - Page {i}\n{body}"
        for i, body in enumerate(page_bodies, 1)
    ]
    cleaned = pdf_service.remove_headers_footers(six_pages)
    assert len(cleaned) == 6

    for idx, page_text in enumerate(cleaned):
        # Repeating header line is removed
        assert "Acme Corp Confidential Policy - Page" not in page_text
        # Unique body content is preserved
        assert page_bodies[idx] in page_text

    # 4-page document (< 5 pages): Header/footer removal must be SKIPPED
    four_pages = [
        f"Acme Corp Confidential Policy - Page {i}\nShort document body {i}."
        for i in range(1, 5)
    ]
    skipped_cleaned = pdf_service.remove_headers_footers(four_pages)
    assert len(skipped_cleaned) == 4
    for i, page_text in enumerate(skipped_cleaned, 1):
        # Under 5 pages: header remains intact
        assert f"Acme Corp Confidential Policy - Page {i}" in page_text


def test_indentation_and_newlines_preserved():
    """
    3. Cleaning:
    - Strip control chars (\x00 etc.) but KEEP \n and \t.
    - Normalize repeated spaces/tabs within a line.
    - Do NOT collapse newlines or strip leading indentation (needed for YAML/code).
    - Unicode NFKC applied.
    """
    raw_code = (
        "apiVersion: v1\x00\n"
        "kind: Pod\n"
        "metadata:\n"
        "    name:   my-backend-pod\n"
        "spec:\n"
        "    containers:\n"
        "      - name:   api-server\n"
        "        image:   nginx:latest\n\n\n"
        "# Section 2\n"
        "Done."
    )

    cleaned = pdf_service.clean_text(raw_code)

    # Control char \x00 removed
    assert "\x00" not in cleaned
    assert "apiVersion: v1" in cleaned

    # Leading indentation preserved
    assert "\n    name: my-backend-pod" in cleaned
    assert "\n      - name: api-server" in cleaned
    assert "\n        image: nginx:latest" in cleaned

    # Repeated spaces within line normalized
    assert "name:   my-backend-pod" not in cleaned
    assert "image:   nginx:latest" not in cleaned

    # Newlines NOT collapsed (triple newline preserved)
    assert "\n\n\n" in cleaned


def test_scanned_image_only_page():
    """
    4. Scanned pages:
    If a page has fewer than 50 characters, set is_scanned=True.
    Does not crash or fail the extraction.
    """
    # Create PDF where page 1 has full text, page 2 is nearly empty (scanned image proxy)
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((50, 72), "This is page 1 with plenty of enterprise knowledge text to exceed 50 characters.", fontsize=11)

    p2 = doc.new_page()
    p2.insert_text((50, 72), "Fig 1.", fontsize=11)  # Only 6 characters

    pdf_bytes = doc.tobytes()
    doc.close()

    records = pdf_service.extract_text_by_pages(pdf_bytes, "scanned_test.pdf")
    assert len(records) == 2
    assert isinstance(records[0], PDFPageRecord)

    # Page 1 is normal
    assert records[0].page_index == 0
    assert records[0].char_count >= 50
    assert records[0].is_scanned is False

    # Page 2 has < 50 chars -> marked as is_scanned=True
    assert records[1].page_index == 1
    assert records[1].char_count < 50
    assert records[1].is_scanned is True


def test_encrypted_pdf_handling():
    """
    5. Encrypted PDF:
    Password-protected PDFs raise PDFEncryptedError, mapped to 400 in API.
    """
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((50, 72), "Top secret content.")
    encrypted_bytes = doc.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="secret123",
        owner_pw="owner123"
    )
    doc.close()

    # Direct service call raises custom PDFEncryptedError
    with pytest.raises(PDFEncryptedError) as exc_info:
        pdf_service.extract_text_by_pages(encrypted_bytes, "secret.pdf")
    assert "encrypted" in str(exc_info.value).lower()

    # API endpoint returns HTTP 400
    client = TestClient(app)
    resp = client.post(
        "/api/documents/upload",
        files={"file": ("secret.pdf", encrypted_bytes, "application/pdf")}
    )
    assert resp.status_code == 400
    assert "encrypted" in resp.json()["detail"].lower()


def test_corrupt_file_handling():
    """
    6. Corrupt file:
    Corrupt PDF stream raises PDFCorruptError, mapped to 422 in API.
    """
    # Starts with %PDF header but is corrupted
    corrupt_bytes = b"%PDF-1.7\n\x00\xff\xfeTRUNCATED_AND_MALFORMED_GARBAGE_BYTES_NO_TRAILER"

    with pytest.raises(PDFCorruptError) as exc_info:
        pdf_service.extract_text_by_pages(corrupt_bytes, "corrupted.pdf")
    assert "corrupt" in str(exc_info.value).lower()

    # API endpoint returns HTTP 422
    client = TestClient(app)
    resp = client.post(
        "/api/documents/upload",
        files={"file": ("corrupted.pdf", corrupt_bytes, "application/pdf")}
    )
    assert resp.status_code == 422
    assert "corrupt" in resp.json()["detail"].lower()


def test_non_pdf_upload_validation():
    """
    7. Non-PDF upload:
    Files missing %PDF magic bytes raise PDFValidationError, mapped to 400 in API.
    """
    plain_text_bytes = b"Hello, this is a plain text file, not a binary PDF document."

    with pytest.raises(PDFValidationError) as exc_info:
        pdf_service.extract_text_by_pages(plain_text_bytes, "notes.pdf")
    assert "magic header" in str(exc_info.value).lower()

    # Empty file
    with pytest.raises(PDFValidationError) as exc_empty:
        pdf_service.extract_text_by_pages(b"", "empty.pdf")
    assert "empty" in str(exc_empty.value).lower()

    # API endpoint returns HTTP 400
    client = TestClient(app)
    resp = client.post(
        "/api/documents/upload",
        files={"file": ("notes.pdf", plain_text_bytes, "application/pdf")}
    )
    assert resp.status_code == 400
    assert "magic header" in resp.json()["detail"].lower()


def test_pdf_headings_extraction_from_outline():
    """
    8. Headings:
    Extract outline TOC from doc.get_toc() with {title, level, page_index}.
    """
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((50, 72), "Chapter 1 Introduction: System Architecture Overview")
    p2 = doc.new_page()
    p2.insert_text((50, 72), "Chapter 2 Implementation: Configuration and Deployment Details")

    # Set native PDF outline table of contents: [lvl, title, page_1_indexed]
    toc = [
        [1, "Introduction Overview", 1],
        [2, "Background Details", 1],
        [1, "Technical Architecture", 2]
    ]
    doc.set_toc(toc)
    pdf_bytes = doc.tobytes()
    doc.close()

    records = pdf_service.extract_text_by_pages(pdf_bytes, "manual.pdf")
    assert len(records) == 2

    headings = pdf_service.last_headings
    assert len(headings) == 3
    assert headings[0].title == "Introduction Overview"
    assert headings[0].level == 1
    assert headings[0].page_index == 0  # 0-based
    assert headings[2].title == "Technical Architecture"
    assert headings[2].page_index == 1


def test_pdf_page_record_backward_compatibility():
    """
    Verify PDFPageRecord supports dict-like get('page') and get('text')
    so downstream chunking_service continues working without breaking.
    """
    record = PDFPageRecord(
        page_index=0,
        page_label="1",
        text="Sample document text.",
        char_count=21,
        is_scanned=False,
        tables_found=0
    )

    # Pydantic attributes
    assert record.page_index == 0
    assert record.page_label == "1"
    assert record.text == "Sample document text."

    # Backward compatibility helpers
    assert record.page == 1
    assert record.get("page", 99) == 1
    assert record.get("text") == "Sample document text."
    assert record["page"] == 1
    assert record["text"] == "Sample document text."
