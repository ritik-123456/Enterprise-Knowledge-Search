import hashlib
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from app.core.config import settings
from app.schemas.rag import DocumentChunk

try:
    import tiktoken
    tokenizer = tiktoken.get_encoding("cl100k_base")
except Exception:
    tokenizer = None


def count_tokens(text: str) -> int:
    """
    Count tokens accurately using tiktoken (cl100k_base),
    with robust regex fallback if tiktoken is not available.
    """
    if tokenizer is not None:
        try:
            return len(tokenizer.encode(text, disallowed_special=()))
        except Exception:
            pass
    # Heuristic fallback: approx 1 token per 0.75 words
    words = text.split()
    return max(1, int(len(words) * 1.33)) if words else 0


KNOWN_REAL_HYPHENS = {
    "kube-system", "kube-public", "kube-node-lease", "kube-proxy", "kube-dns",
    "built-in", "real-time", "read-only", "state-of-the-art", "self-service",
    "zero-trust", "open-source", "client-side", "server-side"
}


def get_embedding_text(chunk: DocumentChunk) -> str:
    """
    Returns formatted contextualized text for embedding: 'doc_name > heading\\n chunk_text'.
    If section_heading is absent: 'doc_name\\n chunk_text'.
    If document_name is absent: 'heading\\n chunk_text'.
    Does not modify chunk.text.
    """
    if chunk.text.startswith("[Document:"):
        return chunk.text

    doc = (chunk.document_name or "").strip()
    heading = (chunk.section_heading or "").strip()
    if doc and heading:
        prefix = f"{doc} > {heading}"
    elif doc:
        prefix = doc
    elif heading:
        prefix = heading
    else:
        prefix = ""

    if prefix:
        return f"{prefix}\n{chunk.text}"
    return chunk.text


def detect_heading_line(line: str) -> Optional[str]:
    """
    Detects if a single line is a recognizable section heading.
    Rules:
    - Must be <= 80 characters.
    - Must not end with a period '.'.
    - Strict regex matching without re.IGNORECASE.
    - Matches Markdown headers (#), numbered sections (1.2 Architecture),
      keyword headings (Section/Chapter/Policy/Summary/etc.), or strict ALL-CAPS titles.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 80 or stripped.endswith("."):
        return None

    # 1. Markdown headings (# Heading, ## Subheading)
    md_match = re.match(r"^#{1,6}\s+([A-Za-z0-9].*)$", stripped)
    if md_match:
        return md_match.group(1).strip()

    # 2. Numbered section titles (e.g., '1. Introduction', '2.3 System Architecture')
    num_match = re.match(r"^[0-9]+(?:\.[0-9]+)*\.?\s+([A-Z].{2,})$", stripped)
    if num_match:
        return stripped

    # 3. Explicit Keyword headings (case-sensitive, <= 80 chars, not ending with '.')
    keyword_match = re.match(
        r"^(?:Section|Chapter|Article|Policy|Summary|Overview|Appendix|Standard|Guideline|Procedure)\b(?:\s+[0-9A-Za-z\-_:]+)?.*$",
        stripped
    )
    if keyword_match:
        return stripped

    # 4. Strict ALL-CAPS titles (at least 4 uppercase characters, digits/spaces/punctuation, NO lowercase)
    if (
        re.match(r"^[A-Z0-9\s\-_:]{4,}$", stripped)
        and re.search(r"[A-Z]{3,}", stripped)
        and not re.search(r"[a-z]", stripped)
    ):
        return stripped

    return None


def is_bullet_or_list_line(line: str) -> bool:
    """Returns True if line represents a bullet list or numbered item."""
    return bool(re.match(r"^\s*(?:[-*•+]|\d+[\.\)])\s+", line.strip()))


def is_table_line(line: str) -> bool:
    """Returns True if line resembles a table row or column-separated data."""
    s = line.strip()
    return "|" in s or "\t" in s


def split_oversize_table(table_text: str, max_tokens: int) -> List[str]:
    """
    Splits an oversized markdown table into smaller sub-tables by rows,
    repeating the table header and separator rows on every split piece.
    """
    lines = [l for l in table_text.strip().splitlines() if l.strip()]
    if len(lines) < 3 or not lines[0].startswith("|") or "---" not in lines[1]:
        return [table_text]

    header_lines = lines[:2]
    header_str = "\n".join(header_lines) + "\n"
    header_tokens = count_tokens(header_str)

    data_rows = lines[2:]
    chunks = []
    current_rows = []
    current_tokens = header_tokens

    for row in data_rows:
        row_tokens = count_tokens(row)
        if current_rows and (current_tokens + row_tokens > max_tokens):
            sub_table = header_str + "\n".join(current_rows)
            chunks.append(sub_table)
            current_rows = [row]
            current_tokens = header_tokens + row_tokens
        else:
            current_rows.append(row)
            current_tokens += row_tokens

    if current_rows:
        chunks.append(header_str + "\n".join(current_rows))

    return chunks if chunks else [table_text]


def strip_headers_footers_and_page_numbers(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Strips repeated headers/footers and standalone page numbers from pages:
    - Only strips lines that appear in top/bottom 3 lines of at least 3 pages (or >= 50% of pages).
    - Standalone page numbers in top/bottom 3 lines are always stripped.
    """
    total_pages = len(pages)
    if total_pages == 0:
        return []

    def is_standalone_page_number(line_text: str) -> bool:
        s = line_text.strip()
        if not s:
            return False
        # Matches 'Page 1', 'pg 2', '1 of 12', '1/12', '- 1 -', '1'
        if re.match(r"^(?:(?:page|pg\.?)\s*)?\d+(?:\s*(?:of|/|-)\s*\d+)?$", s, re.IGNORECASE):
            return True
        if re.match(r"^[-–—]\s*\d+\s*[-–—]$", s):
            return True
        if re.match(r"^\d+$", s):
            return True
        return False

    pages_lines: List[List[str]] = []
    for p in pages:
        raw_text = p.get("text", "") if isinstance(p, dict) or hasattr(p, "get") else getattr(p, "text", "")
        pages_lines.append(raw_text.splitlines())

    # Count candidate lines in top 3 and bottom 3 lines across pages
    line_page_counts: Dict[str, set] = {}
    for p_idx, lines in enumerate(pages_lines):
        non_empty = [line.strip() for line in lines if line.strip()]
        top_3 = non_empty[:3]
        bottom_3 = non_empty[-3:] if len(non_empty) > 3 else []
        candidates = set(top_3 + bottom_3)
        for c in candidates:
            if c and not is_standalone_page_number(c):
                if c not in line_page_counts:
                    line_page_counts[c] = set()
                line_page_counts[c].add(p_idx)

    # Threshold: appear in top/bottom 3 lines of at least 3 pages (or >= 50% of pages)
    lines_to_strip = set()
    for line_text, p_indices in line_page_counts.items():
        count = len(p_indices)
        if count >= 2 and (count >= 3 or (count / total_pages) >= 0.5):
            lines_to_strip.add(line_text)

    cleaned_pages: List[Dict[str, Any]] = []
    for p_idx, p in enumerate(pages):
        page_num = p.get("page", p_idx + 1) if isinstance(p, dict) or hasattr(p, "get") else getattr(p, "page", p_idx + 1)
        raw_lines = pages_lines[p_idx]
        filtered_lines: List[str] = []

        non_empty_indices = [i for i, l in enumerate(raw_lines) if l.strip()]
        top_indices = set(non_empty_indices[:3])
        bottom_indices = set(non_empty_indices[-3:]) if len(non_empty_indices) > 3 else set()
        edge_indices = top_indices | bottom_indices

        for i, line in enumerate(raw_lines):
            stripped = line.strip()
            if not stripped:
                filtered_lines.append("")
                continue

            if i in edge_indices:
                if stripped in lines_to_strip or is_standalone_page_number(stripped):
                    continue

            if is_standalone_page_number(stripped):
                continue

            filtered_lines.append(line)

        cleaned_pages.append({
            "page": page_num,
            "text": "\n".join(filtered_lines)
        })

    return cleaned_pages


def fix_hyphenated_line_breaks(text: str) -> str:
    """
    Rejoins hyphenated broken words across line breaks only when the next
    fragment starts with a lowercase letter (e.g. 'informa-\\ntion' -> 'information').
    Preserves real hyphenated terms like 'kube-system'.
    """
    def _repl(match: re.Match) -> str:
        prefix = match.group(1)
        suffix = match.group(2)
        compound = f"{prefix.lower()}-{suffix.lower()}"
        if compound in KNOWN_REAL_HYPHENS or prefix.lower() == "kube":
            return f"{prefix}-{suffix}"
        return f"{prefix}{suffix}"

    pattern = r'(\b[a-zA-Z]+)-\s*[\r\n]+\s*([a-z]\w*\b)'
    return re.sub(pattern, _repl, text)


class ChunkingService:
    def __init__(
        self,
        chunk_size_tokens: int = settings.CHUNK_SIZE_TOKENS,
        overlap_tokens: int = settings.CHUNK_OVERLAP_TOKENS,
        embedding_model: str = settings.EMBEDDING_MODEL
    ):
        self.chunk_size_tokens = chunk_size_tokens
        self.overlap_tokens = overlap_tokens
        self.embedding_model = embedding_model

    @staticmethod
    def _detect_heading(text: str) -> Optional[str]:
        """
        Detects if the text block starts with a recognizable section heading.
        Tightened regex without re.IGNORECASE.
        """
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            return None
        return detect_heading_line(lines[0])

    @staticmethod
    def get_embedding_text(chunk: DocumentChunk) -> str:
        """Exposes embedding format helper on ChunkingService."""
        return get_embedding_text(chunk)

    @staticmethod
    def _resolve_page_span(
        char_start: int,
        char_end: int,
        page_ranges: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """
        Determines the starting and ending page numbers for a chunk
        from character offsets within the joined document stream.
        """
        if not page_ranges:
            return 1, 1

        p_start = page_ranges[0]["page"]
        p_end = page_ranges[-1]["page"]

        for pr in page_ranges:
            if pr["start"] <= char_start < pr["end"]:
                p_start = pr["page"]
                break
            elif char_start < pr["start"]:
                p_start = pr["page"]
                break

        for pr in reversed(page_ranges):
            if pr["start"] < char_end <= pr["end"]:
                p_end = pr["page"]
                break
            elif char_end > pr["end"]:
                p_end = pr["page"]
                break

        return p_start, max(p_start, p_end)

    def _split_text_into_token_chunks(
        self,
        text: str,
        page_num: int = 1,
        char_base_offset: int = 0,
        page_ranges: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Splits text into chunks sized by tokens (CHUNK_SIZE_TOKENS)
        with sliding-window token overlap (CHUNK_OVERLAP_TOKENS).
        Pre-splits oversized sentences before the chunk-building loop
        so no chunk ever exceeds CHUNK_SIZE_TOKENS.
        """
        if not text.strip():
            return []

        # 1. Split text into initial sentence/block boundaries
        sentence_delimiters = re.finditer(r'(?<=[.!?])\s+|\n{2,}', text)
        raw_blocks: List[Dict[str, Any]] = []
        last_idx = 0

        for match in sentence_delimiters:
            split_idx = match.start()
            s_text = text[last_idx:split_idx].strip()
            if s_text:
                raw_blocks.append({
                    "text": s_text,
                    "char_start": char_base_offset + last_idx,
                    "char_end": char_base_offset + split_idx,
                })
            last_idx = match.end()

        tail = text[last_idx:].strip()
        if tail:
            raw_blocks.append({
                "text": tail,
                "char_start": char_base_offset + last_idx,
                "char_end": char_base_offset + len(text),
            })

        if not raw_blocks:
            return []

        # 2. Oversized block pre-splitting BEFORE the chunk-building loop
        sentences: List[Dict[str, Any]] = []
        for block in raw_blocks:
            b_text = block["text"]
            b_start = block["char_start"]
            b_toks = count_tokens(b_text)

            if b_toks <= self.chunk_size_tokens:
                sentences.append({
                    "text": b_text,
                    "char_start": b_start,
                    "char_end": block["char_end"],
                    "tokens": b_toks
                })
            else:
                # Split oversized block into pieces of at most CHUNK_SIZE_TOKENS by words
                word_matches = list(re.finditer(r'\S+', b_text))
                if not word_matches:
                    continue

                w_idx = 0
                total_w = len(word_matches)
                piece_start_idx = word_matches[0].start()

                while w_idx < total_w:
                    accum_w_end = word_matches[w_idx].end()
                    next_w = w_idx + 1

                    while next_w < total_w:
                        cand_slice = b_text[piece_start_idx:word_matches[next_w].end()]
                        if count_tokens(cand_slice) > self.chunk_size_tokens:
                            break
                        accum_w_end = word_matches[next_w].end()
                        next_w += 1

                    piece_text = b_text[piece_start_idx:accum_w_end].strip()
                    piece_toks = count_tokens(piece_text)

                    # If a single unbroken word exceeds chunk_size_tokens, slice by characters
                    if piece_toks > self.chunk_size_tokens and next_w == w_idx + 1:
                        step_chars = max(10, int(self.chunk_size_tokens * 3.5))
                        for c_pos in range(0, len(piece_text), step_chars):
                            sub_w = piece_text[c_pos:c_pos + step_chars]
                            sentences.append({
                                "text": sub_w,
                                "char_start": b_start + piece_start_idx + c_pos,
                                "char_end": b_start + piece_start_idx + c_pos + len(sub_w),
                                "tokens": count_tokens(sub_w)
                            })
                        w_idx += 1
                        if w_idx < total_w:
                            piece_start_idx = word_matches[w_idx].start()
                        continue

                    sentences.append({
                        "text": piece_text,
                        "char_start": b_start + piece_start_idx,
                        "char_end": b_start + accum_w_end,
                        "tokens": piece_toks
                    })

                    w_idx = next_w
                    if w_idx < total_w:
                        piece_start_idx = word_matches[w_idx].start()

        if not sentences:
            return []

        # 3. Chunk-building loop (no oversized-sentence bypass branch)
        chunks_data: List[Dict[str, Any]] = []
        i = 0
        n = len(sentences)

        while i < n:
            accumulated: List[Dict[str, Any]] = []
            j = i

            while j < n:
                sent = sentences[j]
                cand_text = " ".join([s["text"] for s in accumulated] + [sent["text"]]) if accumulated else sent["text"]
                cand_tokens = count_tokens(cand_text)

                # Stop if adding this sentence would exceed chunk size
                if cand_tokens > self.chunk_size_tokens and accumulated:
                    break

                accumulated.append(sent)
                j += 1

            chunk_text = " ".join(s["text"] for s in accumulated)
            c_start = accumulated[0]["char_start"]
            c_end = accumulated[-1]["char_end"]
            t_count = count_tokens(chunk_text)

            p_start = page_num
            p_end = page_num
            if page_ranges:
                p_start, p_end = self._resolve_page_span(c_start, c_end, page_ranges)

            chunks_data.append({
                "text": chunk_text,
                "char_start": c_start,
                "char_end": c_end,
                "token_count": t_count,
                "page_start": p_start,
                "page_end": p_end
            })

            if j >= n:
                break

            # Sliding window backwards for overlap
            overlap_accum = 0
            step_back = j - 1
            while step_back > i:
                overlap_accum += sentences[step_back]["tokens"]
                if overlap_accum >= self.overlap_tokens:
                    break
                step_back -= 1

            i = max(i + 1, step_back)

        return chunks_data

    def _process_document_legacy(
        self,
        pages: List[Dict[str, Any]],
        doc_name: str,
        document_id: Optional[str] = None
    ) -> List[DocumentChunk]:
        """
        Legacy (v1) sliding-window token chunking.
        1. Strips repeated headers/footers and standalone page numbers.
        2. Rejoins broken hyphenated line breaks.
        3. Detects section headings BEFORE collapsing single newlines and records (char_offset, heading) pairs.
        4. Preserves newlines around headings, bullet lists, and table lines while collapsing single newlines inside prose.
        5. Joins pages into a contiguous text stream with page character offset tracking.
        6. Chunks once across page boundaries with sliding-window overlap.
        7. Assigns each chunk the last detected heading at or before its char_start.
        """
        if not pages:
            return []

        # Generate stable document content hash if not provided
        if not document_id:
            combined_raw = "".join(
                p.get("text", "") if isinstance(p, dict) or hasattr(p, "get") else getattr(p, "text", "")
                for p in pages
            )
            document_id = hashlib.sha256(combined_raw.encode("utf-8")).hexdigest()

        # Step 1: Strip repeated headers, footers, and standalone page numbers
        cleaned_pages = strip_headers_footers_and_page_numbers(pages)

        # Step 2-4: Build unified document text while tracking page ranges and heading offsets
        unified_text_parts: List[str] = []
        page_ranges: List[Dict[str, Any]] = []
        headings_records: List[Tuple[int, str]] = []  # (char_offset, heading)

        current_char_offset = 0
        prose_buffer: List[str] = []

        def flush_prose(target_parts: List[str], base_offset: int) -> int:
            nonlocal prose_buffer
            if not prose_buffer:
                return base_offset
            para_text = " ".join(prose_buffer).strip()
            prose_buffer = []
            if para_text:
                if target_parts and not target_parts[-1].endswith("\n\n"):
                    if target_parts[-1].endswith("\n"):
                        target_parts.append("\n")
                        base_offset += 1
                    else:
                        target_parts.append("\n\n")
                        base_offset += 2
                target_parts.append(para_text + "\n\n")
                base_offset += len(para_text) + 2
            return base_offset

        for p_data in cleaned_pages:
            page_num = p_data["page"]
            page_raw_text = p_data["text"]

            # Fix hyphenated line breaks on page text
            page_text = fix_hyphenated_line_breaks(page_raw_text)

            page_start_offset = current_char_offset
            page_lines = [l.rstrip() for l in page_text.splitlines()]

            # Strip margin padding blank lines from page boundaries
            while page_lines and not page_lines[0].strip():
                page_lines.pop(0)
            while page_lines and not page_lines[-1].strip():
                page_lines.pop()

            for line in page_lines:
                stripped = line.strip()
                if not stripped:
                    current_char_offset = flush_prose(unified_text_parts, current_char_offset)
                    continue

                heading_detected = detect_heading_line(line)
                if heading_detected is not None:
                    # Flush any accumulated prose before starting heading
                    current_char_offset = flush_prose(unified_text_parts, current_char_offset)

                    if unified_text_parts and not unified_text_parts[-1].endswith("\n\n"):
                        if unified_text_parts[-1].endswith("\n"):
                            unified_text_parts.append("\n")
                            current_char_offset += 1
                        else:
                            unified_text_parts.append("\n\n")
                            current_char_offset += 2

                    # Record heading position at the exact character offset
                    headings_records.append((current_char_offset, heading_detected))
                    heading_str = stripped + "\n\n"
                    unified_text_parts.append(heading_str)
                    current_char_offset += len(heading_str)

                elif is_bullet_or_list_line(line) or is_table_line(line):
                    # Preserve formatting for lists and tables
                    current_char_offset = flush_prose(unified_text_parts, current_char_offset)
                    item_str = line + "\n"
                    unified_text_parts.append(item_str)
                    current_char_offset += len(item_str)

                else:
                    # Normal prose line in paragraph - check cross-line/page hyphen rejoining
                    if prose_buffer and prose_buffer[-1].endswith("-") and stripped and stripped[0].islower():
                        prefix_word = prose_buffer[-1].split()[-1][:-1]
                        words = stripped.split()
                        first_suffix = words[0]
                        rest_of_line = stripped[len(first_suffix):].lstrip()
                        joined_word = prefix_word + first_suffix
                        if f"{prefix_word.lower()}-{first_suffix.lower()}" in KNOWN_REAL_HYPHENS:
                            joined_word = f"{prefix_word}-{first_suffix}"
                        prose_buffer[-1] = prose_buffer[-1][:-len(prefix_word)-1] + joined_word
                        if rest_of_line:
                            prose_buffer.append(rest_of_line)
                    else:
                        prose_buffer.append(stripped)

            # At end of page: flush if ending with terminal punctuation; else let prose flow to next page
            if page_lines and page_lines[-1].strip().endswith((".", "!", "?", ":")):
                current_char_offset = flush_prose(unified_text_parts, current_char_offset)

            current_prose_len = sum(len(w) + 1 for w in prose_buffer)
            page_end_offset = current_char_offset + current_prose_len
            page_ranges.append({
                "page": page_num,
                "start": page_start_offset,
                "end": max(page_start_offset, page_end_offset)
            })

        # Flush any remaining prose at the end of the document
        current_char_offset = flush_prose(unified_text_parts, current_char_offset)

        unified_text = "".join(unified_text_parts).strip()
        if not unified_text:
            return []

        # Step 5: Chunk once across the unified document text
        raw_chunks = self._split_text_into_token_chunks(
            text=unified_text,
            char_base_offset=0,
            page_ranges=page_ranges
        )

        # Step 6: Create DocumentChunk instances with carried-forward headings
        all_chunks: List[DocumentChunk] = []

        for chunk_idx, item in enumerate(raw_chunks):
            chunk_text = item["text"]
            content_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
            c_start = item["char_start"]

            # Assign the last heading detected at or before char_start
            assigned_heading: Optional[str] = None
            for h_offset, h_title in headings_records:
                if h_offset <= c_start:
                    assigned_heading = h_title
                else:
                    break

            page_start = item["page_start"]
            page_end = item["page_end"]
            chunk_id = f"{document_id[:12]}_p{page_start}_c{chunk_idx:03d}"

            chunk = DocumentChunk(
                document_id=document_id,
                chunk_id=chunk_id,
                document_name=doc_name,
                page_start=page_start,
                page_end=page_end,
                section_heading=assigned_heading,
                char_start=c_start,
                char_end=item["char_end"],
                token_count=item["token_count"],
                content_hash=content_hash,
                embedding_model=self.embedding_model,
                created_at=datetime.now(timezone.utc),
                text=chunk_text,
                pipeline_version="v1",
                parent_text=None
            )
            all_chunks.append(chunk)

        return all_chunks

    def process_document_parent_child(
        self,
        pages: List[Dict[str, Any]],
        doc_name: str,
        document_id: Optional[str] = None,
        child_chunk_size: Optional[int] = None,
        child_overlap: Optional[int] = None
    ) -> List[DocumentChunk]:
        """
        Structure-aware parent-child (small-to-big) chunking:
        1. Segments document into structural sections based on headings and layout.
        2. Preserves markdown tables and lists intact (splits oversized tables row-by-row repeating headers).
        3. Retains full section text as `parent_text` for LLM grounding.
        4. Generates small, focused child chunks (100-150 tokens) for high-precision vector search.
        5. Prepends context header [Document: ... | Section: ... | Page ...] to each child chunk.
        """
        if not pages:
            return []

        c_size = child_chunk_size or getattr(settings, "CHILD_CHUNK_SIZE_TOKENS", 150)
        c_overlap = child_overlap or getattr(settings, "CHILD_CHUNK_OVERLAP_TOKENS", 30)

        if not document_id:
            combined_raw = "".join(
                p.get("text", "") if isinstance(p, dict) or hasattr(p, "get") else getattr(p, "text", "")
                for p in pages
            )
            document_id = hashlib.sha256(combined_raw.encode("utf-8")).hexdigest()

        cleaned_pages = strip_headers_footers_and_page_numbers(pages)
        if not cleaned_pages:
            return []

        # Step 1: Parse pages into structural sections by heading boundaries
        sections: List[Dict[str, Any]] = []
        current_heading = "Introduction"
        current_blocks: List[Tuple[int, str]] = []

        for p_data in cleaned_pages:
            page_num = p_data.get("page", 1)
            raw_text = fix_hyphenated_line_breaks(p_data.get("text", ""))
            lines = raw_text.splitlines()

            i = 0
            n = len(lines)
            while i < n:
                line = lines[i]
                stripped = line.strip()

                if not stripped:
                    i += 1
                    continue

                heading_cand = detect_heading_line(line)
                if heading_cand is not None:
                    # Flush current section
                    if current_blocks:
                        sec_text = "\n\n".join(b[1] for b in current_blocks).strip()
                        p_min = min(b[0] for b in current_blocks)
                        p_max = max(b[0] for b in current_blocks)
                        if sec_text:
                            sections.append({
                                "heading": current_heading,
                                "text": sec_text,
                                "page_start": p_min,
                                "page_end": p_max,
                                "blocks": current_blocks
                            })
                    current_heading = heading_cand
                    current_blocks = []
                    i += 1
                    continue

                # Table block collection (consecutive lines starting with | or tab)
                if is_table_line(line):
                    table_lines = [line]
                    i += 1
                    while i < n and (is_table_line(lines[i]) or not lines[i].strip()):
                        if lines[i].strip():
                            table_lines.append(lines[i])
                        i += 1
                    table_str = "\n".join(table_lines)
                    current_blocks.append((page_num, table_str))
                    continue

                # Paragraph / List block collection
                para_lines = [line]
                i += 1
                while i < n and lines[i].strip() and not detect_heading_line(lines[i]) and not is_table_line(lines[i]):
                    para_lines.append(lines[i])
                    i += 1
                para_str = "\n".join(para_lines)
                current_blocks.append((page_num, para_str))

        # Flush final accumulated section
        if current_blocks:
            sec_text = "\n\n".join(b[1] for b in current_blocks).strip()
            p_min = min(b[0] for b in current_blocks)
            p_max = max(b[0] for b in current_blocks)
            if sec_text:
                sections.append({
                    "heading": current_heading,
                    "text": sec_text,
                    "page_start": p_min,
                    "page_end": p_max,
                    "blocks": current_blocks
                })

        # Step 2: For each section, produce small child chunks linked to the parent section
        all_chunks: List[DocumentChunk] = []
        global_chunk_idx = 0

        for sec in sections:
            sec_heading = sec["heading"]
            parent_text = sec["text"]
            sec_p_start = sec["page_start"]
            sec_p_end = sec["page_end"]
            sec_tokens = count_tokens(parent_text)

            # If section already fits within child_chunk_size, single chunk
            if sec_tokens <= c_size:
                context_header = f"[Document: {doc_name} | Section: {sec_heading} | Page {sec_p_start}]"
                full_child_text = f"{context_header}\n{parent_text}"
                chunk_id = f"{document_id[:12]}_p{sec_p_start}_c{global_chunk_idx:03d}"
                all_chunks.append(
                    DocumentChunk(
                        document_id=document_id,
                        chunk_id=chunk_id,
                        document_name=doc_name,
                        page_start=sec_p_start,
                        page_end=sec_p_end,
                        section_heading=sec_heading,
                        char_start=0,
                        char_end=len(full_child_text),
                        token_count=count_tokens(full_child_text),
                        content_hash=hashlib.sha256(full_child_text.encode("utf-8")).hexdigest(),
                        embedding_model=self.embedding_model,
                        created_at=datetime.now(timezone.utc),
                        text=full_child_text,
                        pipeline_version="v2",
                        parent_text=parent_text
                    )
                )
                global_chunk_idx += 1
                continue

            # Break blocks down: split oversize tables and long paragraphs into atomic units
            atomic_pieces: List[Tuple[int, str]] = []
            for b_page, b_text in sec["blocks"]:
                if is_table_line(b_text) and count_tokens(b_text) > c_size:
                    split_tables = split_oversize_table(b_text, c_size)
                    for st in split_tables:
                        atomic_pieces.append((b_page, st))
                else:
                    if count_tokens(b_text) > c_size:
                        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', b_text) if s.strip()]
                        for s in sents:
                            atomic_pieces.append((b_page, s))
                    else:
                        atomic_pieces.append((b_page, b_text))

            # Group atomic pieces into child chunks with overlap
            idx = 0
            num_pieces = len(atomic_pieces)
            while idx < num_pieces:
                accum = []
                cur_tokens = 0
                j = idx

                while j < num_pieces:
                    p_page, p_text = atomic_pieces[j]
                    p_toks = count_tokens(p_text)
                    if cur_tokens + p_toks > c_size and accum:
                        break
                    accum.append(atomic_pieces[j])
                    cur_tokens += p_toks
                    j += 1

                if not accum:
                    accum.append(atomic_pieces[idx])
                    j = idx + 1

                chunk_page_start = min(item[0] for item in accum)
                chunk_page_end = max(item[0] for item in accum)
                child_body = "\n\n".join(item[1] for item in accum)
                context_header = f"[Document: {doc_name} | Section: {sec_heading} | Page {chunk_page_start}]"
                full_child_text = f"{context_header}\n{child_body}"

                chunk_id = f"{document_id[:12]}_p{chunk_page_start}_c{global_chunk_idx:03d}"
                all_chunks.append(
                    DocumentChunk(
                        document_id=document_id,
                        chunk_id=chunk_id,
                        document_name=doc_name,
                        page_start=chunk_page_start,
                        page_end=chunk_page_end,
                        section_heading=sec_heading,
                        char_start=0,
                        char_end=len(full_child_text),
                        token_count=count_tokens(full_child_text),
                        content_hash=hashlib.sha256(full_child_text.encode("utf-8")).hexdigest(),
                        embedding_model=self.embedding_model,
                        created_at=datetime.now(timezone.utc),
                        text=full_child_text,
                        pipeline_version="v2",
                        parent_text=parent_text
                    )
                )
                global_chunk_idx += 1

                if j >= num_pieces:
                    break

                # Overlap step back
                overlap_accum = 0
                step_back = j - 1
                while step_back > idx:
                    overlap_accum += count_tokens(atomic_pieces[step_back][1])
                    if overlap_accum >= c_overlap:
                        break
                    step_back -= 1
                idx = max(idx + 1, step_back)

        return all_chunks

    def process_document(
        self,
        pages: List[Dict[str, Any]],
        doc_name: str,
        document_id: Optional[str] = None,
        pipeline_version: Optional[str] = None
    ) -> List[DocumentChunk]:
        """
        Routes document chunking according to pipeline_version and feature flags:
        - 'v2' (default when ENABLE_PARENT_CHILD=True): Structure-aware parent-child chunking.
        - 'v1' (or ENABLE_PARENT_CHILD=False): Legacy sliding-window flat token chunking.
        """
        active_ver = pipeline_version or getattr(settings, "PIPELINE_VERSION", "v2")
        use_parent_child = getattr(settings, "ENABLE_PARENT_CHILD", True) and (active_ver == "v2")

        if use_parent_child:
            return self.process_document_parent_child(pages, doc_name, document_id)
        return self._process_document_legacy(pages, doc_name, document_id)


chunking_service = ChunkingService()
