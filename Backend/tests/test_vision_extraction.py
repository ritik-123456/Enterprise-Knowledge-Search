import os
import sys
import pytest
import pymupdf

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.services.image_vision_service import image_vision_service, extract_nearby_figure_captions


def create_sample_pdf_with_image() -> bytes:
    """Generates an in-memory PDF with text and an embedded raster figure."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)

    # Insert heading and textbook paragraph
    text = (
        "Chapter 3: Distributed System Architecture\n\n"
        "In Kubernetes, the control plane manages worker nodes through the kube-apiserver.\n"
        "Figure 3.1: High-level Kubernetes control plane architecture\n"
        "The diagram below illustrates communication between etcd, scheduler, and nodes.\n"
    )
    page.insert_text(pymupdf.Point(50, 50), text, fontsize=12)

    # Create a 200x200 sample image pixmap and insert it
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 200), 1)
    # Fill with a distinctive pattern
    page.insert_image(pymupdf.Rect(50, 150, 250, 350), pixmap=pix)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_figure_caption_extraction():
    sample_text = (
        "Introduction to Biology\n"
        "Figure 1.2: Structure of a plant cell and chloroplasts\n"
        "Some explanatory text follows.\n"
        "Fig. 3A - Photosynthetic electron transport chain.\n"
        "Diagram 4: Cellular respiration cycle\n"
    )
    captions = extract_nearby_figure_captions(sample_text)
    assert len(captions) == 3
    assert "Figure 1.2" in captions[0]
    assert "Fig. 3A" in captions[1]
    assert "Diagram 4" in captions[2]


def test_extract_and_index_images_fallback():
    """
    Tests extraction and chunk creation without relying on live Gemini network,
    verifying fallback behavior, file saving, and chunk creation.
    """
    pdf_bytes = create_sample_pdf_with_image()
    doc_id = "test_doc_vision_12345"
    doc_name = "test_textbook.pdf"

    # Ensure clean state
    image_vision_service.cleanup_document_images(doc_id)

    chunks = image_vision_service.extract_and_index_images(
        pdf_bytes=pdf_bytes,
        document_id=doc_id,
        doc_name=doc_name,
        user_id="test_user"
    )

    assert len(chunks) >= 1
    chunk = chunks[0]
    assert chunk.document_id == doc_id
    assert chunk.document_name == doc_name
    assert chunk.page_start == 1
    assert "![Figure" in chunk.text or "![" in chunk.text
    assert f"/api/documents/images/{doc_id}/" in chunk.text

    # Verify file was written to disk
    storage_dir = image_vision_service.get_document_storage_dir(doc_id)
    files = os.listdir(storage_dir)
    assert len(files) >= 1
    assert files[0].endswith((".png", ".jpeg", ".jpg"))

    # Verify cleanup
    image_vision_service.cleanup_document_images(doc_id)
    if os.path.exists(storage_dir):
        assert len(os.listdir(storage_dir)) == 0


def test_strip_chunk_id_citations_preserves_images():
    from app.services.rag_service import strip_chunk_id_citations

    text_with_image = (
        "Here is the control plane diagram:\n\n"
        "![Figure 3.1: Architecture](/api/documents/images/doc123/page_1_fig_01.png)\n\n"
        "The API server coordinates all cluster requests [test_doc_p1_c001]. "
        "High confidence: verified."
    )

    cleaned = strip_chunk_id_citations(text_with_image)

    # Chunk ID and confidence tag should be stripped
    assert "[test_doc_p1_c001]" not in cleaned
    assert "High confidence" not in cleaned

    # Image markdown MUST be preserved intact
    assert "![Figure 3.1: Architecture](/api/documents/images/doc123/page_1_fig_01.png)" in cleaned
