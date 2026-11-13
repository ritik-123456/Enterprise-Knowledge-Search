import base64
import concurrent.futures
import hashlib
import io
import logging
import os
import re
import shutil
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

import pymupdf

from app.core.config import settings
from app.schemas.rag import DocumentChunk
from app.services.chunking_service import count_tokens

logger = logging.getLogger(__name__)


def extract_nearby_figure_captions(page_text: str) -> List[str]:
    """
    Extracts potential figure captions from page text, e.g.:
    - "Figure 3.1: High-level Kubernetes architecture"
    - "Fig 12 - Electron transport chain in mitochondria"
    - "Diagram 4: Database replication topology"
    """
    captions = []
    if not page_text:
        return captions

    pattern = re.compile(
        r'^\s*(?:Figure|Fig\.?|Diagram|Chart|Illustration|Graph|Plate)\s+([0-9A-Za-z\.\-_]+)(?:[:\.\-–—\s]+)(.*)$',
        re.IGNORECASE
    )

    for line in page_text.splitlines():
        line_clean = line.strip()
        if not line_clean or len(line_clean) > 200:
            continue
        match = pattern.match(line_clean)
        if match:
            captions.append(line_clean)

    return captions


class ImageVisionService:
    def __init__(self):
        self._ensure_storage_dir()

    def _ensure_storage_dir(self) -> str:
        base_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", settings.DOCUMENT_IMAGES_PATH)
        )
        os.makedirs(base_dir, exist_ok=True)
        return base_dir

    def get_document_storage_dir(self, document_id: str) -> str:
        base_dir = self._ensure_storage_dir()
        doc_dir = os.path.join(base_dir, document_id)
        os.makedirs(doc_dir, exist_ok=True)
        return doc_dir

    def cleanup_document_images(self, document_id: str) -> None:
        """Deletes all stored images for a document when the document is removed."""
        try:
            base_dir = self._ensure_storage_dir()
            doc_dir = os.path.join(base_dir, document_id)
            if os.path.exists(doc_dir):
                # Delete all image files inside
                for fname in os.listdir(doc_dir):
                    fpath = os.path.join(doc_dir, fname)
                    try:
                        if os.path.isfile(fpath) or os.path.islink(fpath):
                            os.unlink(fpath)
                        elif os.path.isdir(fpath):
                            shutil.rmtree(fpath, ignore_errors=True)
                    except Exception as f_err:
                        logger.debug(f"Could not delete {fpath}: {f_err}")
                try:
                    os.rmdir(doc_dir)
                except Exception:
                    # On Windows/OneDrive, if directory lock prevents immediate rmdir, all files are purged
                    pass
                logger.info(f"Cleaned up image storage for document {document_id}")
        except Exception as e:
            logger.warning(f"Failed to cleanup images for document {document_id}: {e}")

    def _get_vision_client(self):
        """Initializes OpenAI client configured for Gemini multimodal endpoint."""
        from openai import OpenAI
        active_key = settings.active_api_key
        if not active_key:
            return None

        client_kwargs: Dict[str, Any] = {"api_key": active_key}
        if settings.is_gemini:
            client_kwargs["base_url"] = settings.OPENAI_BASE_URL or "https://generativelanguage.googleapis.com/v1beta/openai/"
        elif settings.OPENAI_BASE_URL:
            client_kwargs["base_url"] = settings.OPENAI_BASE_URL

        return OpenAI(**client_kwargs)

    def describe_image(
        self,
        image_bytes: bytes,
        image_ext: str,
        page_num: int,
        doc_name: str,
        nearby_caption: Optional[str] = None,
        max_retries: int = 2
    ) -> str:
        """
        Uses Gemini Flash Vision to produce a detailed academic/technical description
        of the diagram, figure, chart, or illustration.
        """
        client = self._get_vision_client()
        if not client:
            return (
                f"Figure on Page {page_num} of {doc_name}."
                + (f" Caption: {nearby_caption}" if nearby_caption else "")
            )

        # Standardize mime type
        ext_clean = image_ext.lower().replace(".", "").strip()
        if ext_clean in ("jpg", "jpeg"):
            mime_type = "image/jpeg"
        elif ext_clean == "png":
            mime_type = "image/png"
        elif ext_clean == "webp":
            mime_type = "image/webp"
        else:
            mime_type = "image/png"

        b64_img = base64.b64encode(image_bytes).decode("utf-8")

        caption_hint = f"\nRelevant caption identified on page: \"{nearby_caption}\"" if nearby_caption else ""
        system_instruction = (
            "You are an expert academic and technical textbook reader. "
            "Analyze this textbook figure, diagram, chart, or scientific illustration in detail.\n\n"
            "Guidelines:\n"
            "1. State clearly what type of visual this is (e.g. Architecture Diagram, Process Flowchart, Scientific Illustration, Graph/Plot, Schematic, Mathematical Formula).\n"
            "2. Transcribe and describe all key components, labels, flow of arrows, axes, annotations, and numeric values.\n"
            "3. Explain the core concept, mechanism, or principle demonstrated in this figure.\n"
            "4. Conclude with a clear 1-2 sentence summary of key takeaways."
        )

        user_content = [
            {
                "type": "text",
                "text": f"Document: {doc_name} (Page {page_num}){caption_hint}\n\nAnalyze this visual figure according to the guidelines:"
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64_img}"}
            }
        ]

        # Use vision model (prefer gemini-flash-lite-latest or settings.VISION_MODEL)
        model_name = settings.VISION_MODEL or settings.LLM_MODEL
        if not ("gemini" in model_name.lower()) and settings.is_gemini:
            model_name = "gemini-flash-lite-latest"

        for attempt in range(1, max_retries + 1):
            try:
                resp = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_content}
                    ],
                    max_tokens=600,
                    temperature=0.2
                )
                if resp.choices and resp.choices[0].message and resp.choices[0].message.content:
                    description = resp.choices[0].message.content.strip()
                    logger.info(
                        f"Vision analyzed image on page {page_num} of '{doc_name}' ({len(description)} chars)."
                    )
                    return description
            except Exception as exc:
                err_str = str(exc).lower()
                is_transient = any(t in err_str for t in ["429", "rate", "limit", "timeout", "503", "502"])
                if is_transient and attempt < max_retries:
                    time.sleep(1.0 * attempt)
                    continue
                logger.warning(f"Vision API analysis failed on page {page_num} (attempt {attempt}): {exc}")

        # Fallback when vision API fails or is rate limited
        fallback = f"Figure on Page {page_num} of {doc_name}."
        if nearby_caption:
            fallback += f" Caption: {nearby_caption}"
        return fallback

    def extract_and_index_images(
        self,
        pdf_bytes: bytes,
        document_id: str,
        doc_name: str,
        user_id: str = ""
    ) -> List[DocumentChunk]:
        """
        Extracts diagrams, figures, and textbook images from PDF bytes,
        analyzes them with Gemini Vision, saves them to disk, and creates
        searchable DocumentChunk objects.
        """
        if not getattr(settings, "ENABLE_VISION_EXTRACTION", True):
            logger.info("Vision extraction is disabled by config (ENABLE_VISION_EXTRACTION=False).")
            return []

        doc_dir = self.get_document_storage_dir(document_id)
        image_chunks: List[DocumentChunk] = []

        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            logger.warning(f"Could not open PDF for vision extraction: {e}")
            return []

        # Pass 1: Catalog all images and count frequency of image hashes across pages
        # (to filter out recurring company/publisher logos or watermarks)
        img_page_occurrences: Dict[str, set] = {}
        page_image_candidates: List[Dict[str, Any]] = []

        try:
            total_pages = doc.page_count
            max_allowed = getattr(settings, "VISION_MAX_IMAGES_PER_DOC", 30)
            min_dim = getattr(settings, "VISION_MIN_IMAGE_DIMENSION", 120)

            for page_idx in range(total_pages):
                page_num = page_idx + 1
                page = doc[page_idx]
                page_text = page.get_text("text") or ""
                captions = extract_nearby_figure_captions(page_text)

                # 1. Inspect raster images on page
                image_infos = page.get_image_info(xrefs=True)
                for img_info in image_infos:
                    xref = img_info.get("xref", 0)
                    if xref == 0:
                        continue
                    w = img_info.get("width", 0)
                    h = img_info.get("height", 0)

                    # Filter out small icons, spacer pixels, or line dividers
                    if w < min_dim or h < min_dim:
                        continue
                    if (w * h) < 15000:
                        continue
                    ratio = w / max(1, h)
                    if ratio < 0.12 or ratio > 8.0:
                        continue

                    # Extract raw image bytes to compute content hash
                    try:
                        extracted = doc.extract_image(xref)
                        raw_bytes = extracted.get("image", b"")
                        if not raw_bytes or len(raw_bytes) < 512:
                            continue

                        img_hash = hashlib.md5(raw_bytes).hexdigest()
                        img_page_occurrences.setdefault(img_hash, set()).add(page_num)

                        page_image_candidates.append({
                            "type": "raster",
                            "page_num": page_num,
                            "xref": xref,
                            "hash": img_hash,
                            "bytes": raw_bytes,
                            "ext": extracted.get("ext", "png"),
                            "width": w,
                            "height": h,
                            "captions": captions
                        })
                    except Exception as ext_err:
                        logger.debug(f"Could not extract image xref {xref} on page {page_num}: {ext_err}")

                # 2. Inspect vector drawings (e.g., flowcharts, block diagrams drawn with PDF vector paths)
                # If a page has NO raster images, but has vector drawings and mentions figure/diagram keywords
                has_raster = any(c["page_num"] == page_num for c in page_image_candidates)
                if not has_raster and captions:
                    try:
                        drawings = page.get_drawings()
                        if len(drawings) >= 15:  # Substantial vector diagram
                            # Render page pixmap at 150 DPI
                            pix = page.get_pixmap(dpi=150)
                            rendered_bytes = pix.tobytes("png")
                            if rendered_bytes and len(rendered_bytes) > 10000:
                                d_hash = hashlib.md5(rendered_bytes).hexdigest()
                                img_page_occurrences.setdefault(d_hash, set()).add(page_num)
                                page_image_candidates.append({
                                    "type": "vector_diagram",
                                    "page_num": page_num,
                                    "xref": 0,
                                    "hash": d_hash,
                                    "bytes": rendered_bytes,
                                    "ext": "png",
                                    "width": pix.width,
                                    "height": pix.height,
                                    "captions": captions
                                })
                    except Exception as vec_err:
                        logger.debug(f"Could not render vector diagram on page {page_num}: {vec_err}")

        finally:
            doc.close()

        # Pass 2: Filter out recurring publisher logos (present on 3 or more pages)
        valid_figures: List[Dict[str, Any]] = []
        for cand in page_image_candidates:
            h = cand["hash"]
            if len(img_page_occurrences.get(h, set())) >= 3:
                # Watermark or recurring logo
                continue
            valid_figures.append(cand)

        if not valid_figures:
            logger.info(f"No qualifying textbook figures or diagrams found in '{doc_name}'.")
            return []

        # Enforce max limit per document to prevent exceeding quotas
        if len(valid_figures) > max_allowed:
            logger.info(
                f"Found {len(valid_figures)} figures in '{doc_name}'. Truncating to top {max_allowed}."
            )
            valid_figures = valid_figures[:max_allowed]

        logger.info(
            f"Processing {len(valid_figures)} textbook figures from '{doc_name}' with Gemini Vision..."
        )

        # Pass 3: Save images, generate vision descriptions, and build DocumentChunks in parallel
        def _process_single_figure(fig_tuple: Tuple[int, Dict[str, Any]]) -> Optional[DocumentChunk]:
            idx, fig = fig_tuple
            page_num = fig["page_num"]
            ext = fig["ext"]
            filename = f"page_{page_num}_fig_{idx:02d}.{ext}"
            file_path = os.path.join(doc_dir, filename)

            # Save image file to storage
            try:
                with open(file_path, "wb") as f:
                    f.write(fig["bytes"])
            except Exception as write_err:
                logger.warning(f"Failed to save image {filename}: {write_err}")
                return None

            # Public URL path
            image_url = f"/api/documents/images/{document_id}/{filename}"

            # Nearby caption if any
            nearby_cap = fig["captions"][0] if fig["captions"] else None

            # Multimodal Vision Analysis
            description = self.describe_image(
                image_bytes=fig["bytes"],
                image_ext=ext,
                page_num=page_num,
                doc_name=doc_name,
                nearby_caption=nearby_cap
            )

            fig_title = nearby_cap or f"Figure {idx} (Page {page_num})"

            # Build rich chunk text containing markdown image and deep visual description
            chunk_text = (
                f"[Document: {doc_name} | Visual Figure: {fig_title} | Page {page_num}]\n"
                f"![{fig_title}]({image_url})\n\n"
                f"**Figure Description:**\n{description}"
            )

            chunk_id = f"{document_id[:12]}_img_p{page_num}_{idx:02d}"
            token_count = count_tokens(chunk_text)

            return DocumentChunk(
                document_id=document_id,
                user_id=user_id,
                chunk_id=chunk_id,
                document_name=doc_name,
                page_start=page_num,
                page_end=page_num,
                section_heading=f"Visual Figure: {fig_title}",
                char_start=0,
                char_end=len(chunk_text),
                token_count=token_count,
                content_hash=hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                embedding_model=settings.EMBEDDING_MODEL,
                created_at=datetime.now(timezone.utc),
                text=chunk_text,
                pipeline_version="v2",
                parent_text=chunk_text
            )

        max_workers = min(6, max(1, len(valid_figures)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            figure_items = list(enumerate(valid_figures, start=1))
            chunk_results = list(executor.map(_process_single_figure, figure_items))

        image_chunks = [c for c in chunk_results if c is not None]

        logger.info(
            f"Successfully created {len(image_chunks)} multimodal visual figure chunks for '{doc_name}'."
        )
        return image_chunks


image_vision_service = ImageVisionService()
