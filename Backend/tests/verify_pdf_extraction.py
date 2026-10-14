import os
import sys
import logging
import pytest
import pymupdf

# Ensure Backend directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.pdf_service import (
    pdf_service,
    PDFExtractionError,
    PDFValidationError,
    PDFCorruptError,
    PDFProcessingError
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verify_pdf_extraction")


def test_normal_text_pdf_extraction():
    """Test a: Normal text PDF returns pages with non-empty text."""
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((50, 72), "Enterprise Knowledge Search Architecture Overview.\nThis document details the multi-cluster Kubernetes deployment guidelines.", fontsize=11)
    p2 = doc.new_page()
    p2.insert_text((50, 72), "Security and Authentication Baseline.\nZero-trust mTLS encryption is strictly enforced across all service mesh nodes.", fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()

    records = pdf_service.extract_text_by_pages(pdf_bytes, "normal_test.pdf")
    assert len(records) == 2, f"Expected 2 pages, got {len(records)}"
    assert records[0]["page"] == 1
    assert "Enterprise Knowledge Search" in records[0]["text"]
    assert records[1]["page"] == 2
    assert "Security and Authentication" in records[1]["text"]
    print("  [PASS] Test (a): Normal text PDF successfully extracted 2 pages with non-empty text.")


def test_empty_or_scanned_pdf_raises_extraction_error():
    """Test b: Empty/image-only PDF (< 50 chars) raises PDFExtractionError."""
    # Generate an image-only / empty PDF in code (only 10 characters total)
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((50, 72), "Fig 1.2", fontsize=11)  # Only 7 characters (< 50 threshold)
    pdf_bytes = doc.tobytes()
    doc.close()

    try:
        pdf_service.extract_text_by_pages(pdf_bytes, "scanned_empty.pdf")
        assert False, "Should have raised PDFExtractionError for < 50 chars!"
    except PDFExtractionError as err:
        assert "OCR" in str(err) or "under 50 characters" in str(err)
        print(f"  [PASS] Test (b): Image-only/scanned PDF raised PDFExtractionError as expected: '{err}'")


def test_garbage_bytes_raise_extraction_error():
    """Test c: Garbage bytes raise PDFExtractionError (not a placeholder result)."""
    garbage_bytes = b"%PDF-1.7\n\x00\xffCORRUPT_NON_STREAM_DATA_WITH_MISSING_CROSS_REFERENCE_TABLE"
    try:
        pdf_service.extract_text_by_pages(garbage_bytes, "garbage.pdf")
        assert False, "Should have raised PDFExtractionError for corrupt bytes!"
    except PDFExtractionError as err:
        assert not isinstance(err, list)
        print(f"  [PASS] Test (c): Garbage bytes raised PDFExtractionError as expected: '{err}'")


def inspect_real_pdf_eks_handbook():
    """Inspect real PDF from uploads: eks_handbook.pdf."""
    real_pdf_path = r"C:\Users\ritik\Downloads\eks_handbook.pdf"
    if not os.path.exists(real_pdf_path):
        print(f"\n[SKIP] Real PDF not found at {real_pdf_path}.")
        return

    print("\n" + "=" * 70)
    print(f"REAL PDF EXTRACTION INSPECTION: {os.path.basename(real_pdf_path)}")
    print("=" * 70)

    with open(real_pdf_path, "rb") as f:
        pdf_bytes = f.read()

    records = pdf_service.extract_text_by_pages(pdf_bytes, "eks_handbook.pdf")

    print(f"Total Pages Extracted : {len(records)}")
    print("\nCharacters Per Page:")
    for r in records:
        char_count = len(r["text"].strip())
        print(f"  Page {r['page']:2d}: {char_count:5d} characters")

    print("\nFirst 800 Characters of Page 1:")
    print("-" * 70)
    page_1_snippet = records[0]["text"][:800]
    print(page_1_snippet)
    print("-" * 70)
    print("\n[PASS] Real PDF extraction inspection completed successfully.")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("UNIT TESTS: PDF EXTRACTION VALIDATION")
    print("=" * 70)
    test_normal_text_pdf_extraction()
    test_empty_or_scanned_pdf_raises_extraction_error()
    test_garbage_bytes_raise_extraction_error()
    inspect_real_pdf_eks_handbook()
