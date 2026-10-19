import io
import logging
import re
import shutil
import unicodedata
from typing import List, Dict, Any, Optional, Tuple, Union

import pymupdf

from app.core.config import settings
from app.schemas.rag import PDFPageRecord, PDFHeading

logger = logging.getLogger(__name__)


def check_ocr_available() -> bool:
    """Verifies whether Tesseract OCR or OCR engine binary is available on system PATH."""
    return (shutil.which("tesseract") is not None) or (shutil.which("tesseract.exe") is not None)

# Known technical hyphenated compound terms that should keep their hyphen
KNOWN_REAL_HYPHENS = {
    "kube-system", "kube-public", "kube-node-lease", "kube-proxy", "kube-dns",
    "built-in", "real-time", "read-only", "state-of-the-art", "self-service",
    "zero-trust", "open-source", "client-side", "server-side"
}


class PDFProcessingError(Exception):
    """Base exception for all PDF processing errors."""
    pass


class PDFExtractionError(PDFProcessingError):
    """Raised when PDF text extraction fails, is password-protected, has < 50 chars, or requires OCR."""
    pass


class PDFValidationError(PDFProcessingError):
    """Raised for non-PDF or empty files (mapped to HTTP 400)."""
    pass


class PDFOversizedError(PDFProcessingError):
    """Raised when file exceeds MAX_UPLOAD_MB (mapped to HTTP 413)."""
    pass


class PDFEncryptedError(PDFExtractionError):
    """Raised when PDF is encrypted or password-protected (mapped to HTTP 400/422)."""
    pass


class PDFPageLimitError(PDFProcessingError):
    """Raised when page count exceeds MAX_PAGES (mapped to HTTP 400)."""
    pass


class PDFCorruptError(PDFExtractionError):
    """Raised when PDF is corrupt or unparseable (mapped to HTTP 422)."""
    pass


class PDFService:
    def __init__(self):
        pass

    def validate_pdf_bytes(self, pdf_bytes: bytes, file_name: str = "") -> None:
        """
        Validates magic bytes and file limits before parsing.
        """
        if not pdf_bytes:
            raise PDFValidationError(f"File '{file_name or 'document'}' is empty (0 bytes).")

        # 1. Enforce MAX_UPLOAD_MB limit
        max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
        if len(pdf_bytes) > max_bytes:
            raise PDFOversizedError(
                f"File size ({round(len(pdf_bytes) / (1024 * 1024), 2)} MB) exceeds "
                f"maximum allowed limit of {settings.MAX_UPLOAD_MB} MB."
            )

        # 2. Check %PDF magic bytes in the first 1024 bytes
        header = pdf_bytes[:1024]
        if b"%PDF" not in header:
            raise PDFValidationError(
                f"File '{file_name or 'document'}' is not a valid PDF document "
                f"(missing %PDF magic header)."
            )

    @staticmethod
    def clean_text(text: str) -> str:
        """
        Cleans extracted text according to strict formatting rules:
        - Unicode NFKC normalization
        - Strip control characters (\\x00 etc.) while strictly PRESERVING \\n and \\t
        - Normalize only repeated spaces/tabs within a line
        - Never collapse newlines or strip leading indentation (needed for YAML/code/chunking)
        """
        if not text:
            return ""

        # 1. Unicode NFKC
        text = unicodedata.normalize("NFKC", text)

        # 2. Strip non-printable control characters, but keep \n, \t, and \r
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

        # 3. Normalize repeated spaces/tabs within each line, preserving leading indentation
        lines = text.split("\n")
        cleaned_lines = []
        for line in lines:
            leading_match = re.match(r'^[ \t]*', line)
            indent = leading_match.group(0) if leading_match else ""
            content = line[len(indent):]
            normalized_content = re.sub(r'[ \t]+', ' ', content)
            cleaned_lines.append(indent + normalized_content)

        return "\n".join(cleaned_lines)

    _clean_text = clean_text

    @staticmethod
    def fix_hyphenation(text: str) -> str:
        """
        Rejoins hyphenated broken words across line breaks (e.g. 'config-\\nuration' -> 'configuration')
        only when the next line starts with a lowercase letter.
        Preserves real hyphens like 'kube-\\nsystem' and hyphens followed by an uppercase letter or digit.
        """
        if not text:
            return ""

        def _hyphen_replacer(match: re.Match) -> str:
            prefix = match.group(1)
            suffix = match.group(2)
            compound = f"{prefix.lower()}-{suffix.lower()}"
            if compound in KNOWN_REAL_HYPHENS or prefix.lower() == "kube":
                return f"{prefix}-{suffix}"
            return f"{prefix}{suffix}"

        pattern = r'([a-zA-Z]+)-\n([a-z]+)'
        return re.sub(pattern, _hyphen_replacer, text)

    @staticmethod
    def remove_headers_footers(page_texts: List[str]) -> List[str]:
        """
        Removes lines that repeat on more than 60% of pages (compared after stripping digits).
        Skips this for documents under 5 pages.
        """
        if len(page_texts) < 5:
            return page_texts

        total_pages = len(page_texts)
        threshold = total_pages * 0.60

        line_page_counts: Dict[str, int] = {}
        for text in page_texts:
            seen_on_page = set()
            for line in text.split("\n"):
                normalized = re.sub(r'\d+', '', line).strip()
                if normalized and normalized not in seen_on_page:
                    seen_on_page.add(normalized)
                    line_page_counts[normalized] = line_page_counts.get(normalized, 0) + 1

        repeating_patterns = {
            pat for pat, count in line_page_counts.items()
            if count > threshold
        }

        if not repeating_patterns:
            return page_texts

        filtered_pages: List[str] = []
        for text in page_texts:
            kept_lines = []
            for line in text.split("\n"):
                normalized = re.sub(r'\d+', '', line).strip()
                if normalized in repeating_patterns:
                    continue
                kept_lines.append(line)
            filtered_pages.append("\n".join(kept_lines))

        return filtered_pages

    @staticmethod
    def extract_tables_as_markdown(page: pymupdf.Page) -> Tuple[str, int]:
        """
        Extracts tables from a page using PyMuPDF's find_tables() and converts them to Markdown.
        Returns (combined_markdown_tables, tables_found_count).
        """
        try:
            tabs = page.find_tables()
            table_count = len(tabs.tables) if hasattr(tabs, "tables") else 0
            if table_count == 0:
                return "", 0

            markdown_tables = []
            for tab in tabs.tables:
                try:
                    if hasattr(tab, "to_markdown"):
                        md = tab.to_markdown()
                        if md and md.strip():
                            markdown_tables.append(md.strip())
                            continue

                    extracted_rows = tab.extract()
                    if extracted_rows:
                        header = [str(c or "").strip() for c in extracted_rows[0]]
                        sep = ["---"] * max(1, len(header))
                        rows = [
                            "| " + " | ".join(str(c or "").strip() for c in r) + " |"
                            for r in extracted_rows[1:]
                        ]
                        md = f"| {' | '.join(header)} |\n| {' | '.join(sep)} |\n" + "\n".join(rows)
                        markdown_tables.append(md)
                except Exception as tab_err:
                    logger.warning(f"Error converting table on page {page.number}: {tab_err}")

            return "\n\n".join(markdown_tables), table_count
        except Exception as e:
            logger.warning(f"Table detection failed on page {page.number}: {e}")
            return "", 0

    @staticmethod
    def extract_headings(doc: pymupdf.Document) -> List[PDFHeading]:
        """
        Builds a list of {title, level, page_index} from the PDF outline (doc.get_toc()).
        If no outline exists, falls back to font-size heuristics.
        """
        headings: List[PDFHeading] = []

        try:
            toc = doc.get_toc()
            if toc:
                for item in toc:
                    if len(item) >= 3:
                        level = int(item[0])
                        title = str(item[1]).strip()
                        page_num = int(item[2])
                        if title:
                            headings.append(PDFHeading(
                                title=title,
                                level=level,
                                page_index=max(0, page_num - 1)
                            ))
                if headings:
                    return headings
        except Exception as toc_err:
            logger.warning(f"Failed extracting PDF outline TOC: {toc_err}")

        for page_idx in range(doc.page_count):
            try:
                page = doc[page_idx]
                blocks_dict = page.get_text("dict").get("blocks", [])
                font_sizes = []

                for b in blocks_dict:
                    if "lines" in b:
                        for l in b["lines"]:
                            for s in l.get("spans", []):
                                if s.get("text", "").strip():
                                    font_sizes.append(s.get("size", 12))

                if not font_sizes:
                    continue

                body_size = max(set(font_sizes), key=font_sizes.count) if font_sizes else 12.0

                for b in blocks_dict:
                    if "lines" in b:
                        for l in b["lines"]:
                            line_text = "".join(s.get("text", "") for s in l.get("spans", [])).strip()
                            if not line_text or len(line_text) < 3 or len(line_text) > 100:
                                continue

                            spans = [s for s in l.get("spans", []) if s.get("text", "").strip()]
                            if not spans:
                                continue

                            line_size = max(s.get("size", 12) for s in spans)
                            if line_size >= body_size * 1.25 and not line_text.endswith("."):
                                level = 1 if line_size >= body_size * 1.5 else 2
                                headings.append(PDFHeading(
                                    title=line_text,
                                    level=level,
                                    page_index=page_idx
                                ))
            except Exception as h_err:
                logger.warning(f"Heading heuristic failed on page {page_idx}: {h_err}")

        return headings

    def extract_text_by_pages(
        self,
        pdf_bytes: bytes,
        file_name: str = "",
        return_headings: bool = False
    ) -> Union[List[PDFPageRecord], Tuple[List[PDFPageRecord], List[PDFHeading]]]:
        """
        Extracts text from a PDF document page by page.
        - Primary extractor: PyMuPDF (page.get_text('text', sort=True)).
        - Backup extractor: pypdf (used only if PyMuPDF returns no text).
        - Validates encryption, page limit, and corruption.
        - Raises PDFExtractionError if text < 50 chars (OCR required), password-protected, or extraction fails.
        - Returns list of PDFPageRecord (supporting dict-like ['page'] and ['text']).
        """
        self.validate_pdf_bytes(pdf_bytes, file_name)

        extracted_records: List[PDFPageRecord] = []
        headings: List[PDFHeading] = []
        empty_pages: List[int] = []
        total_chars = 0

        # -------------------------------------------------------------
        # 1. Primary extractor: PyMuPDF
        # -------------------------------------------------------------
        pymupdf_available = True
        doc = None
        open_failure_err = None
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception as open_err:
            logger.warning(f"PyMuPDF open failed for '{file_name}': {open_err}")
            open_failure_err = open_err
            pymupdf_available = False

        if pymupdf_available and doc is not None:
            try:
                # Check encryption
                if doc.is_encrypted or doc.needs_pass:
                    # Attempt empty password authentication first
                    auth_ok = False
                    try:
                        auth_ok = doc.authenticate("")
                    except Exception:
                        pass

                    if not auth_ok and (doc.is_encrypted or doc.needs_pass):
                        raise PDFEncryptedError(
                            f"PDF document '{file_name or 'document'}' is encrypted or password-protected."
                        )

                # Check page limit
                if doc.page_count > settings.MAX_PAGES:
                    raise PDFPageLimitError(
                        f"Document contains {doc.page_count} pages, exceeding max allowed {settings.MAX_PAGES} pages."
                    )

                headings = self.extract_headings(doc)

                # Layout-aware extraction via pymupdf4llm when enabled
                layout_chunks = None
                if getattr(settings, "ENABLE_LAYOUT_PARSER", True):
                    try:
                        import pymupdf4llm
                        layout_chunks = pymupdf4llm.to_markdown(doc, page_chunks=True)
                    except Exception as llm_err:
                        logger.warning(f"pymupdf4llm layout extraction failed for '{file_name}': {llm_err}. Using standard extractor.")
                        layout_chunks = None

                if layout_chunks and len(layout_chunks) == doc.page_count:
                    for item in layout_chunks:
                        meta = item.get("metadata", {})
                        page_num = meta.get("page", 1)
                        page_idx = page_num - 1
                        raw_text = item.get("text", "") or ""
                        tables_found = len(item.get("tables", []))

                        cleaned = self.clean_text(raw_text)
                        cleaned = self.fix_hyphenation(cleaned)
                        char_len = len(cleaned.strip())

                        is_scanned = char_len < 50
                        if is_scanned:
                            if check_ocr_available():
                                try:
                                    page = doc[page_idx]
                                    ocr_tp = page.get_textpage_ocr(language="eng", dpi=150)
                                    ocr_text = ocr_tp.extractText()
                                    if ocr_text and len(ocr_text.strip()) > char_len:
                                        cleaned = self.clean_text(ocr_text)
                                        char_len = len(cleaned.strip())
                                        is_scanned = char_len < 50
                                except Exception as ocr_err:
                                    logger.warning(f"OCR execution failed on page {page_num}: {ocr_err}")
                            else:
                                logger.warning(
                                    f"File '{file_name or 'document'}' page {page_num}: has under 50 characters, "
                                    f"but Tesseract OCR dependencies are not installed on system PATH. Degrading gracefully."
                                )

                        if char_len == 0:
                            empty_pages.append(page_num)
                        else:
                            total_chars += char_len
                            extracted_records.append(PDFPageRecord(
                                page_index=page_idx,
                                page_label=str(page_num),
                                text=cleaned,
                                char_count=char_len,
                                is_scanned=is_scanned,
                                tables_found=tables_found
                            ))
                else:
                    for page_idx in range(doc.page_count):
                        page = doc[page_idx]
                        page_num = page_idx + 1

                        page_label = ""
                        if hasattr(page, "get_label"):
                            page_label = page.get_label()
                        if not page_label:
                            page_label = str(page_num)

                        # Extract text with layout sorting
                        raw_text = page.get_text("text", sort=True) or ""

                        # Table markdown extraction
                        table_md, tables_found = self.extract_tables_as_markdown(page)
                        if table_md:
                            raw_text = raw_text.strip() + "\n\n" + table_md if raw_text.strip() else table_md

                        cleaned = self.clean_text(raw_text)
                        cleaned = self.fix_hyphenation(cleaned)

                        char_len = len(cleaned.strip())
                        is_scanned = char_len < 50
                        if is_scanned and not check_ocr_available():
                            logger.warning(
                                f"File '{file_name or 'document'}' page {page_num}: has under 50 characters, "
                                f"but Tesseract OCR dependencies are not installed on system PATH. Degrading gracefully."
                            )

                        if char_len == 0:
                            empty_pages.append(page_num)
                        else:
                            total_chars += char_len
                            extracted_records.append(PDFPageRecord(
                                page_index=page_idx,
                                page_label=page_label,
                                text=cleaned,
                                char_count=char_len,
                                is_scanned=is_scanned,
                                tables_found=tables_found
                            ))
            finally:
                doc.close()

        # -------------------------------------------------------------
        # 2. Backup extractor: pypdf (only if PyMuPDF returned no text)
        # -------------------------------------------------------------
        if not extracted_records or total_chars == 0:
            logger.info(
                f"PyMuPDF extracted no text from '{file_name or 'document'}'. "
                f"Attempting backup extraction using pypdf..."
            )
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))

                if reader.is_encrypted:
                    try:
                        reader.decrypt("")
                    except Exception:
                        pass
                    if reader.is_encrypted:
                        raise PDFEncryptedError(
                            f"PDF document '{file_name or 'document'}' is encrypted or password-protected."
                        )

                pypdf_records: List[PDFPageRecord] = []
                pypdf_empty: List[int] = []
                pypdf_chars = 0

                for page_idx, page in enumerate(reader.pages):
                    page_num = page_idx + 1
                    raw_text = page.extract_text() or ""
                    cleaned = self.clean_text(raw_text)
                    cleaned = self.fix_hyphenation(cleaned)

                    char_len = len(cleaned.strip())
                    if char_len == 0:
                        pypdf_empty.append(page_num)
                    else:
                        pypdf_chars += char_len
                        pypdf_records.append(PDFPageRecord(
                            page_index=page_idx,
                            page_label=str(page_num),
                            text=cleaned,
                            char_count=char_len,
                            is_scanned=char_len < 50,
                            tables_found=0
                        ))

                if pypdf_records and pypdf_chars > 0:
                    extracted_records = pypdf_records
                    empty_pages = pypdf_empty
                    total_chars = pypdf_chars
            except PDFExtractionError:
                raise
            except Exception as pypdf_err:
                logger.warning(f"Backup extractor pypdf failed for '{file_name}': {pypdf_err}")

        # -------------------------------------------------------------
        # 3. Log warnings for pages with empty text (partially scanned)
        # -------------------------------------------------------------
        if empty_pages:
            logger.warning(
                f"File '{file_name or 'document'}': Detected empty extracted text on pages: {empty_pages} "
                f"(possible blank or scanned pages)."
            )

        # -------------------------------------------------------------
        # 4. Enforce strict non-fake extraction validation
        # -------------------------------------------------------------
        if not extracted_records or total_chars == 0:
            if open_failure_err is not None:
                raise PDFCorruptError(
                    f"PDF document '{file_name or 'document'}' is corrupt or unreadable: {open_failure_err}"
                )
            raise PDFExtractionError(
                f"Failed to extract readable text from '{file_name or 'document'}'. "
                f"The document may be corrupted, empty, or contain only scanned images."
            )

        if total_chars < 50:
            raise PDFExtractionError(
                f"Extracted text from '{file_name or 'document'}' is under 50 characters ({total_chars} characters found). "
                f"The document appears to be scanned or image-only and requires OCR."
            )

        logger.info(
            f"Successfully extracted text from '{file_name or 'document'}': "
            f"{len(extracted_records)} pages with text, {total_chars} total characters."
        )

        if return_headings:
            return extracted_records, headings
        return extracted_records

    def extract_text_and_headings(
        self,
        pdf_bytes: bytes,
        file_name: str = ""
    ) -> Tuple[List[PDFPageRecord], List[PDFHeading]]:
        """
        Extracts both text pages and document outline headings.
        Returns (records, headings) without storing headings on singleton state.
        """
        return self.extract_text_by_pages(pdf_bytes, file_name=file_name, return_headings=True)


pdf_service = PDFService()
