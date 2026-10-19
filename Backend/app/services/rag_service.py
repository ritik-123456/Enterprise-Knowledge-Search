import logging
import re
import time
from typing import List, Optional, Tuple, Dict, Any, Set

from rank_bm25 import BM25Okapi, BM25Plus

from app.core.config import settings
from app.core.constants import RELATIVE_SCORE_CUTOFF_RATIO, compute_retrieval_strength
from app.services.vector_store import vector_store
from app.services.hybrid_retriever import (
    corpus_bm25_index,
    compute_rrf_fusion,
    cross_encoder_reranker,
    apply_mmr_diversity,
    apply_multi_doc_balance,
    deduplicate_parents,
)
from app.services.query_decomposition import query_decomposition_service
from app.schemas.rag import AskAIResponse, CitationSource, DocumentChunk

logger = logging.getLogger(__name__)


def is_reasoning_model(model_name: str) -> bool:
    """
    Checks if model belongs to a reasoning family (e.g., o1, o3, o-series)
    which rejects or ignores the custom temperature parameter and requires max_completion_tokens.
    """
    m = model_name.lower().strip()
    return m.startswith("o1") or m.startswith("o3") or "-o1" in m or "-o3" in m


def tokenize_query_and_text(text: str) -> List[str]:
    """
    Tokenizes text for BM25 keyword matching while preserving exact terms,
    error codes (ERR_502), ARNs (arn:aws:iam::123), and CLI flags (--kubeconfig).
    """
    tokens = re.findall(r'[a-zA-Z0-9_\-\.:/]+', text.lower())
    return [t for t in tokens if len(t) > 1 or t.isalnum()]


def compute_reciprocal_rank_fusion(
    candidates: List[Tuple[DocumentChunk, float]],
    question: str,
    k: float = 60.0
) -> List[Tuple[DocumentChunk, float, float]]:
    """
    Computes reciprocal rank fusion (RRF) combining vector similarity rank
    with BM25 keyword rank over the same candidate chunks.
    Formula: RRF_score = 1/(k + r_vector) + 1/(k + r_bm25)
    Returns (chunk, vector_score, rrf_score) sorted descending by rrf_score.
    """
    if not candidates:
        return []

    # 1. Vector rank: candidates are already sorted descending by vector score
    vector_ranks: Dict[str, int] = {}
    for rank, (chunk, _) in enumerate(candidates, start=1):
        vector_ranks[chunk.chunk_id] = rank

    # 2. BM25 rank: tokenize chunks and query (including section heading for title queries)
    corpus_tokens = [
        tokenize_query_and_text(f"{chunk.section_heading or ''} {chunk.text}")
        for chunk, _ in candidates
    ]
    query_tokens = tokenize_query_and_text(question)

    bm25_ranks: Dict[str, int] = {}
    if query_tokens and corpus_tokens:
        try:
            bm25 = BM25Okapi(corpus_tokens)
            scores = list(bm25.get_scores(query_tokens))
            # Fall back to BM25Plus if all scores are 0 (e.g. small corpus <= 3)
            if max(scores, default=0.0) == 0.0:
                bm25 = BM25Plus(corpus_tokens)
                scores = list(bm25.get_scores(query_tokens))
        except Exception as e:
            logger.debug(f"BM25 scoring notice: {e}")
            scores = [0.0] * len(candidates)
    else:
        scores = [0.0] * len(candidates)

    # Rank positive BM25 matches; non-matching items (score <= 0) receive lowest rank
    positive_matches = [(idx, scores[idx]) for idx in range(len(scores)) if scores[idx] > 0]
    positive_sorted = sorted(positive_matches, key=lambda x: x[1], reverse=True)

    current_rank = 1
    for i, (idx, score) in enumerate(positive_sorted):
        if i > 0 and score == positive_sorted[i - 1][1]:
            bm25_ranks[candidates[idx][0].chunk_id] = bm25_ranks[candidates[positive_sorted[i - 1][0]][0].chunk_id]
        else:
            bm25_ranks[candidates[idx][0].chunk_id] = current_rank
        current_rank += 1

    # Any candidate with no keyword match receives bottom rank
    bottom_rank = len(candidates)
    for idx in range(len(candidates)):
        cid = candidates[idx][0].chunk_id
        if cid not in bm25_ranks:
            bm25_ranks[cid] = bottom_rank

    # 3. Merge with Reciprocal Rank Fusion
    fused: List[Tuple[DocumentChunk, float, float]] = []
    for chunk, v_score in candidates:
        v_r = vector_ranks.get(chunk.chunk_id, len(candidates))
        b_r = bm25_ranks.get(chunk.chunk_id, bottom_rank)
        rrf_score = (1.0 / (k + v_r)) + (1.0 / (k + b_r))
        fused.append((chunk, v_score, rrf_score))

    # Sort by rrf_score descending, tie-break by vector score
    fused.sort(key=lambda x: (x[2], x[1]), reverse=True)
    return fused


def extract_cited_chunk_ids(text: str) -> List[str]:
    """
    Extracts cited chunk identifiers from LLM generated answer text.
    Handles bracket formats: [chunk_id], [chunk1, chunk2], [Chunk ID: ...], etc.
    """
    cited = []
    seen = set()

    # 1. Bracketed expressions e.g. [doc_p1_c000], [chunk1, chunk2]
    for bracket in re.findall(r'\[(.*?)\]', text):
        cleaned = re.sub(r'chunk\s*id\s*:\s*', '', bracket, flags=re.IGNORECASE)
        for part in re.split(r'[,;\s]+', cleaned):
            part = part.strip().strip("'\"()[]:")
            if part and part not in seen:
                seen.add(part)
                cited.append(part)

    # 2. Pattern matching for standard chunk IDs e.g. prefix_p1_c000
    for match in re.findall(r'\b[a-zA-Z0-9_\-]+_p\d+_c\d+\b', text):
        if match not in seen:
            seen.add(match)
            cited.append(match)

    return cited


def strip_chunk_id_citations(text: str) -> str:
    """
    Removes raw internal chunk ID citations such as [3ab80ad6529b_p1_c004] from answer text
    for clean user experience while preserving punctuation and spacing.
    """
    if not text:
        return ""
    # 1. Bracketed chunk IDs e.g. [3ab80ad6529b_p1_c004] or [doc_p1_c001]
    cleaned = re.sub(
        r'\s*\[\s*(?:chunk\s*id\s*:\s*)?[a-zA-Z0-9_\-]+_p\d+_c\d+(?:\s*,\s*(?:chunk\s*id\s*:\s*)?[a-zA-Z0-9_\-]+_p\d+_c\d+)*\s*\]',
        '',
        text,
        flags=re.IGNORECASE
    )
    # 2. General bracket with _p and _c chunk ID pattern
    cleaned = re.sub(r'\s*\[\s*[^\]]*_p\d+_c\d+[^\]]*\s*\]', '', cleaned)
    # 3. Strip any certainty/confidence prefixes or meta-tags (e.g. "high confidence")
    cleaned = re.sub(r'(?i)\(?\bhigh\s+confidence\b:?\)?\s*', '', cleaned)
    # 4. Clean up spaces before punctuation
    cleaned = re.sub(r'\s+([.,;:!?])', r'\1', cleaned)
    return cleaned.strip()


SNIPPET_STOP_WORDS = {
    "what", "is", "the", "of", "in", "and", "to", "a", "an", "for",
    "on", "with", "as", "by", "at", "from", "or", "that", "this", "it",
    "are", "be", "was", "were", "has", "have", "had", "does", "do", "did",
    "how", "can", "could", "should", "would", "which", "where", "when", "why",
    "who", "i", "we", "you", "they", "our", "their", "my", "your", "name"
}


def extract_sentences(text: str) -> List[str]:
    """
    Splits chunk text into individual sentences while preserving sentence content.
    Handles headings, newlines, and punctuation cleanly.
    """
    raw_lines = [line.strip() for line in text.split("\n") if line.strip()]
    sentences: List[str] = []
    for line in raw_lines:
        parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"\'`])', line)
        for part in parts:
            p = part.strip()
            if p:
                sentences.append(p)
    return sentences if sentences else [text.strip()]


def build_citation_snippet(
    chunk_text: str,
    question: str,
    answer: str,
    max_chars: int = 300
) -> str:
    """
    Builds a citation snippet from the sentence (or two) in the cited chunk that best
    matches the question terms and the model answer.

    1. Splits chunk into sentences and scores each sentence using term overlap
       with question and answer (and BM25 keyword weighting).
    2. Selects the top matching sentence and includes one sentence of context before
       or after that fits within the ~300 character limit.
    3. Adds '...' only where text was actually trimmed from the chunk boundaries.
    """
    sentences = extract_sentences(chunk_text)
    if not sentences:
        return ""
    if len(sentences) == 1:
        s = sentences[0]
        if len(s) <= max_chars:
            return s
        cutoff = s[:max_chars - 3].rfind(" ")
        if cutoff > max_chars // 2:
            return s[:cutoff].rstrip(".,; ") + "..."
        return s[:max_chars - 3].rstrip() + "..."

    # Clean citations e.g. [chunk_id] out of the answer for term scoring
    clean_answer = re.sub(r'\[.*?\]', '', answer)
    q_tokens = [t for t in tokenize_query_and_text(question) if t not in SNIPPET_STOP_WORDS]
    a_tokens = [t for t in tokenize_query_and_text(clean_answer) if t not in SNIPPET_STOP_WORDS]
    query_tokens = q_tokens + a_tokens

    corpus_tokens = [tokenize_query_and_text(s) for s in sentences]
    bm25_scores = [0.0] * len(sentences)
    if query_tokens and any(corpus_tokens):
        try:
            bm25 = BM25Okapi(corpus_tokens)
            bm25_scores = list(bm25.get_scores(query_tokens))
        except Exception:
            pass

    q_set = set(q_tokens)
    a_set = set(a_tokens)

    total_scores: List[float] = []
    for idx, s in enumerate(sentences):
        s_tokens = set(tokenize_query_and_text(s))
        overlap_score = 0.0
        for tok in s_tokens:
            if tok in a_set:
                overlap_score += 3.0
            if tok in q_set:
                overlap_score += 2.0
        total_scores.append(bm25_scores[idx] + overlap_score)

    best_idx = max(range(len(sentences)), key=lambda i: total_scores[i])
    best_sent = sentences[best_idx]

    start_idx = best_idx
    end_idx = best_idx

    has_prev = best_idx > 0
    has_next = best_idx < len(sentences) - 1

    if has_prev and has_next:
        prev_score = total_scores[best_idx - 1]
        next_score = total_scores[best_idx + 1]
        prev_len = len(best_sent) + 1 + len(sentences[best_idx - 1])
        next_len = len(best_sent) + 1 + len(sentences[best_idx + 1])

        # Prefer context with higher match score that fits within max_chars
        if next_score >= prev_score and next_len <= max_chars:
            end_idx = best_idx + 1
        elif prev_len <= max_chars:
            start_idx = best_idx - 1
        elif next_len <= max_chars:
            end_idx = best_idx + 1
    elif has_next:
        if len(best_sent) + 1 + len(sentences[best_idx + 1]) <= max_chars:
            end_idx = best_idx + 1
    elif has_prev:
        if len(best_sent) + 1 + len(sentences[best_idx - 1]) <= max_chars:
            start_idx = best_idx - 1

    selected_text = " ".join(sentences[start_idx : end_idx + 1])
    trimmed_start = start_idx > 0
    trimmed_end = end_idx < len(sentences) - 1

    if len(selected_text) > max_chars:
        cutoff = selected_text[:max_chars - 3].rfind(" ")
        if cutoff > max_chars // 2:
            selected_text = selected_text[:cutoff].rstrip(".,; ")
        else:
            selected_text = selected_text[:max_chars - 3].rstrip()
        trimmed_end = True

    prefix = "... " if trimmed_start else ""
    suffix = " ..." if trimmed_end else ""

    return f"{prefix}{selected_text}{suffix}"


class RAGService:
    @staticmethod
    def _create_not_found_response(question: str, start_time: float) -> AskAIResponse:
        """Returns standard response when topic is not found in documents."""
        elapsed = round(time.time() - start_time, 2)
        not_found_msg = (
            f"Information regarding '{question}' was not found in the uploaded documents. "
            f"The topic may not be covered in the available documentation."
        )
        return AskAIResponse(
            question=question,
            answer=not_found_msg,
            citations=[],
            answerable=False,
            lead=not_found_msg,
            key_points=[
                "Please upload the relevant PDF documentation using the Attach button.",
                "Verify your query keywords match terminology in the uploaded policy or handbook."
            ],
            confidence="0%",
            response_time=f"{elapsed}s",
            sources_used=0,
            sources=[]
        )

    @staticmethod
    def _create_failure_response(question: str, start_time: float, message: str) -> AskAIResponse:
        """Returns clean failure response upon unrecoverable API errors."""
        elapsed = round(time.time() - start_time, 2)
        return AskAIResponse(
            question=question,
            answer=message,
            citations=[],
            answerable=False,
            lead=message,
            key_points=[
                "An error occurred while contacting the AI inference service.",
                "Please check your API status or retry your question."
            ],
            confidence="0%",
            response_time=f"{elapsed}s",
            sources_used=0,
            sources=[]
        )

    def _call_openai_with_retries(self, client, create_kwargs: Dict[str, Any], max_retries: int = 3) -> Optional[str]:
        """Calls OpenAI with retries for transient errors (rate limit, timeout, empty response)."""
        kwargs = dict(create_kwargs)
        for attempt in range(1, max_retries + 1):
            try:
                resp = client.chat.completions.create(**kwargs)
                if not resp.choices or not resp.choices[0].message:
                    if attempt < max_retries:
                        time.sleep(0.5 * attempt)
                        continue
                    return None

                content = resp.choices[0].message.content
                if content is None or not content.strip():
                    if attempt < max_retries:
                        time.sleep(0.5 * attempt)
                        continue
                    return None

                return content.strip()
            except Exception as exc:
                err_text = str(exc).lower()

                # Dynamic fallback for models rejecting temperature or max_tokens
                if "temperature" in err_text and "temperature" in kwargs:
                    kwargs.pop("temperature", None)
                    continue
                if "max_tokens" in err_text and "max_tokens" in kwargs:
                    kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
                    continue

                # If a Gemini model hits quota or 404, fall back to gemini-flash-lite-latest
                if ("429" in err_text or "quota" in err_text or "404" in err_text) and "gemini" in kwargs.get("model", "").lower():
                    if kwargs.get("model") != "gemini-flash-lite-latest":
                        logger.warning(f"Gemini model '{kwargs.get('model')}' returned quota/error; switching to 'gemini-flash-lite-latest'")
                        kwargs["model"] = "gemini-flash-lite-latest"
                        continue

                is_transient = any(
                    term in err_text
                    for term in ["rate_limit", "ratelimit", "timeout", "timed out", "connection", "429", "503", "502"]
                )
                if is_transient and attempt < max_retries:
                    time.sleep(0.5 * (2 ** (attempt - 1)))
                    continue
                else:
                    logger.error(f"OpenAI completion failed after {attempt} attempts: {exc}")
                    return None
        return None

    def _answer_query_legacy(
        self,
        question: str,
        user_id: str,
        doc_filter: Optional[List[str]] = None,
        document_id: Optional[str] = None
    ) -> AskAIResponse:
        start_time = time.time()

        # Step 1: Broad retrieval: fetch RETRIEVE_K candidates from vector store
        candidates = vector_store.search(
            query=question,
            user_id=user_id,
            k=settings.RETRIEVE_K,
            doc_filter=doc_filter,
            document_id=document_id,
            min_similarity=settings.MIN_SIMILARITY
        )

        if not candidates:
            logger.info(f"No candidates retrieved from vector store for question: '{question}'")
            return self._create_not_found_response(question, start_time)

        # Log each candidate's vector score
        logger.info(f"Broad retrieval found {len(candidates)} candidates for question: '{question}'")
        for chunk, v_score in candidates:
            page_info = f"Page {chunk.page_start}" if chunk.page_start == chunk.page_end else f"Pages {chunk.page_start}-{chunk.page_end}"
            logger.info(
                f"Candidate chunk: id='{chunk.chunk_id}', score={v_score:.4f}, "
                f"document='{chunk.document_name}', {page_info}"
            )

        # Step 2: Hybrid Retrieval & Reciprocal Rank Fusion over candidate chunks
        # Combines dense vector similarity rank with BM25 keyword matching rank.
        # Short/title queries and exact terms are boosted without being penalized.
        fused_candidates = compute_reciprocal_rank_fusion(candidates, question)

        # Step 3: Apply relative score cutoff to filter chunks scoring far below top candidate,
        # while ALWAYS preserving exact BM25 keyword matches and short/title queries.
        top_v_score = max(score for _, score in candidates)
        relative_threshold = top_v_score * RELATIVE_SCORE_CUTOFF_RATIO

        filtered_top_chunks = []
        for chunk, v_score, rrf_score in fused_candidates:
            is_keyword_match = any(
                t in (f"{chunk.section_heading or ''} {chunk.text}").lower()
                for t in tokenize_query_and_text(question)
                if t not in SNIPPET_STOP_WORDS
            )
            if v_score >= relative_threshold or is_keyword_match or top_v_score <= 0.10:
                filtered_top_chunks.append((chunk, v_score, rrf_score))
            else:
                logger.info(
                    f"Dropped chunk '{chunk.chunk_id}' with score {v_score:.4f} "
                    f"below relative cutoff {relative_threshold:.4f}"
                )

        # Keep the best TOP_K_CHUNKS after fusion & relative filtering
        top_chunks = (filtered_top_chunks if filtered_top_chunks else fused_candidates)[:settings.TOP_K_CHUNKS]
        if not top_chunks:
            logger.info(f"No chunks found after hybrid fusion for question: '{question}'")
            return self._create_not_found_response(question, start_time)

        retrieved_map = {chunk.chunk_id: (chunk, v_score) for chunk, v_score, _ in top_chunks}
        retrieved_chunks = [chunk for chunk, _, _ in top_chunks]

        # Step 4: Calculate Retrieval Strength based on top score and margin over second result (Requirement 6)
        top_score = top_chunks[0][1]
        second_score = top_chunks[1][1] if len(top_chunks) > 1 else None
        retrieval_strength = compute_retrieval_strength(top_score, second_score)
        logger.info(
            f"Retrieval strength computed: '{retrieval_strength}' "
            f"(top_score={top_score:.4f}, second_score={f'{second_score:.4f}' if second_score is not None else 'None'})"
        )

        # Step 5: Context preparation with explicit Chunk ID labels & proper page formatting (Requirement 7)
        context_blocks = []
        for idx, (chunk, v_score, _) in enumerate(top_chunks):
            heading_info = f" ({chunk.section_heading})" if chunk.section_heading else ""
            page_info = f"Page {chunk.page_start}" if chunk.page_start == chunk.page_end else f"Pages {chunk.page_start}-{chunk.page_end}"
            context_blocks.append(
                f"[Chunk ID: {chunk.chunk_id} | Document: {chunk.document_name} | {page_info}{heading_info}]\n"
                f"{chunk.text}"
            )
        context_text = "\n\n".join(context_blocks)

        # Step 6: Verify API key (Requirement 1 - No silent fake answer fallback)
        active_key = settings.active_api_key
        if not active_key:
            logger.warning("Neither OPENAI_API_KEY nor GEMINI_API_KEY is configured or empty. Cannot synthesize LLM answer.")
            return self._create_failure_response(
                question=question,
                start_time=start_time,
                message="OpenAI API key is not configured (or GEMINI_API_KEY). Please set in your environment to generate answers."
            )

        # Step 7: Answer synthesis with OpenAI / Gemini
        try:
            from openai import OpenAI
            client_kwargs: Dict[str, Any] = {"api_key": active_key}
            if settings.is_gemini:
                client_kwargs["base_url"] = settings.OPENAI_BASE_URL or "https://generativelanguage.googleapis.com/v1beta/openai/"
            elif settings.OPENAI_BASE_URL:
                client_kwargs["base_url"] = settings.OPENAI_BASE_URL

            client = OpenAI(**client_kwargs)

            # Determine active model
            if settings.is_gemini and not ("gemini" in settings.LLM_MODEL.lower()):
                active_model = "gemini-3.8-flash"
            else:
                active_model = settings.LLM_MODEL

            system_prompt = (
                "You are an enterprise AI knowledge assistant. Answer the user's question "
                "strictly and factually based ONLY on the provided context excerpts.\n\n"
                "Rules:\n"
                "1. Answer ONLY using facts directly stated in the context excerpts. Do NOT extrapolate or assume.\n"
                "2. Cite the relevant chunk_id inline in brackets immediately following each fact, policy, or claim (e.g. '[chunk_id]').\n"
                "3. If the context does not contain sufficient information to answer the question, state clearly: "
                "'Information regarding this topic was not found in the uploaded documents.'\n"
                "4. When answering, provide a direct factual answer. If the context contains a sequence, steps, or numbered items, preserve the numbered list.\n"
                "5. Do NOT include meta-commentary, confidence scores, or certainty declarations (never write 'high confidence' or confidence metrics)."
            )

            user_prompt = f"Context Excerpts:\n{context_text}\n\nQuestion: {question}"

            create_kwargs = {
                "model": active_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
            }

            if is_reasoning_model(active_model):
                create_kwargs["max_completion_tokens"] = settings.LLM_MAX_TOKENS
                if active_model.lower().startswith(("o1-preview", "o1-mini")):
                    create_kwargs["messages"] = [
                        {"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}
                    ]
            else:
                if settings.LLM_TEMPERATURE is not None:
                    create_kwargs["temperature"] = settings.LLM_TEMPERATURE
                create_kwargs["max_tokens"] = settings.LLM_MAX_TOKENS

            logger.info(
                f"Calling AI chat completion ({'Gemini' if settings.is_gemini else 'OpenAI'}): model='{create_kwargs['model']}', "
                f"temperature={create_kwargs.get('temperature')}, "
                f"max_tokens={create_kwargs.get('max_tokens') or create_kwargs.get('max_completion_tokens')}, "
                f"messages={len(create_kwargs['messages'])}"
            )

            answer_content = self._call_openai_with_retries(client, create_kwargs)
            if not answer_content:
                logger.error("OpenAI chat completion returned None/empty content after retries.")
                return self._create_failure_response(
                    question=question,
                    start_time=start_time,
                    message="AI service encountered an error or timed out. Please try again later."
                )

            # Step 8: Strict Citation Validation (Requirement 4)
            raw_cited_ids = extract_cited_chunk_ids(answer_content)
            valid_citations: List[CitationSource] = []
            valid_ids_seen = set()

            for cid in raw_cited_ids:
                if cid in retrieved_map:
                    if cid not in valid_ids_seen:
                        valid_ids_seen.add(cid)
                        chunk, v_score = retrieved_map[cid]
                        snippet = build_citation_snippet(
                            chunk_text=chunk.text,
                            question=question,
                            answer=answer_content,
                            max_chars=300
                        )
                        valid_citations.append(
                            CitationSource(
                                chunk_id=chunk.chunk_id,
                                source_name=chunk.document_name,
                                page_start=chunk.page_start,
                                page_end=chunk.page_end,
                                snippet=snippet,
                                score=round(v_score, 3),
                                id=len(valid_citations) + 1,
                                section_heading=chunk.section_heading
                            )
                        )
                else:
                    logger.warning(f"Dropping invalid cited chunk_id '{cid}' not in retrieved context set.")

            is_insufficient = (
                not valid_citations
                or answer_content.strip().lower().startswith("information regarding this topic was not found")
                or (
                    len(answer_content.strip()) < 180
                    and any(
                        term in answer_content.lower()
                        for term in [
                            "not found in the uploaded documents",
                            "does not contain sufficient information",
                            "cannot be determined from the excerpts",
                            "not mentioned in the provided context"
                        ]
                    )
                )
            )

            if is_insufficient:
                logger.info("No valid citations found in answer or answer declared insufficient. Setting answerable=False.")
                return self._create_not_found_response(question, start_time)

            # Step 9: Parse answer & key points (Requirements 2 & 3)
            # Never truncate or extract from chunks. Return the model's full answer.
            # Preserve numbered lists like "1. Control plane, 2. add-ons".
            lines = [l.strip() for l in answer_content.split("\n") if l.strip()]
            bullet_lines = [l for l in lines if l.startswith(("- ", "* ", "• "))]

            if bullet_lines:
                first_bullet_idx = next(i for i, l in enumerate(lines) if l.startswith(("- ", "* ", "• ")))
                lead_parts = lines[:first_bullet_idx]
                lead = " ".join(lead_parts) if lead_parts else lines[0]
                key_points = [re.sub(r"^[-*•]\s*", "", l).strip() for l in bullet_lines]
            else:
                lead = answer_content
                key_points = []

            clean_answer = strip_chunk_id_citations(answer_content)
            clean_lead = strip_chunk_id_citations(lead)
            clean_key_points = [strip_chunk_id_citations(kp) for kp in key_points if strip_chunk_id_citations(kp)]

            measured_time = f"{round(time.time() - start_time, 2)}s"

            return AskAIResponse(
                question=question,
                answer=clean_answer,
                citations=valid_citations,
                answerable=True,
                lead=clean_lead,
                key_points=clean_key_points,
                confidence=retrieval_strength,
                response_time=measured_time,
                sources_used=len(valid_citations),
                sources=valid_citations,
                retrieved_chunks=retrieved_chunks
            )
        except Exception as e:
            logger.error(f"OpenAI execution error: {e}", exc_info=True)
            return self._create_failure_response(
                question=question,
                start_time=start_time,
                message=f"AI service encountered an unhandled error ({type(e).__name__}): {e}"
            )

    def _answer_query_v2(
        self,
        question: str,
        user_id: str,
        doc_filter: Optional[List[str]] = None,
        document_id: Optional[str] = None
    ) -> AskAIResponse:
        """
        Improved RAG pipeline (v2):
        1. Query classification & decomposition into 2-5 standalone sub-questions.
        2. Corpus-wide hybrid retrieval (Dense Qdrant + BM25 + RRF) with exact filter parity.
        3. Cross-encoder reranking per sub-question with input length limits.
        4. Parent deduplication for small-to-big retrieval.
        5. Guaranteed minimum representation for multi-doc/comparison queries.
        6. Post-rerank MMR diversity filtering.
        7. Parent-child context resolution (passing rich parent section to LLM).
        8. Upgraded generation prompt with comparison tables and explicit sub-question answers.
        """
        start_time = time.time()
        active_key = settings.active_api_key
        if not active_key:
            return self._create_failure_response(
                question=question,
                start_time=start_time,
                message="OpenAI API key is not configured (or GEMINI_API_KEY). Please set in your environment to generate answers."
            )

        try:
            from openai import OpenAI
            client_kwargs: Dict[str, Any] = {"api_key": active_key}
            if settings.is_gemini:
                client_kwargs["base_url"] = settings.OPENAI_BASE_URL or "https://generativelanguage.googleapis.com/v1beta/openai/"
            elif settings.OPENAI_BASE_URL:
                client_kwargs["base_url"] = settings.OPENAI_BASE_URL

            client = OpenAI(**client_kwargs)

            # Determine active model
            if settings.is_gemini and not ("gemini" in settings.LLM_MODEL.lower()):
                active_model = "gemini-flash-lite-latest"
            else:
                active_model = settings.LLM_MODEL

            # Stage 1: Query Analysis & Decomposition
            t_decomp_0 = time.time()
            if getattr(settings, "ENABLE_QUERY_DECOMPOSITION", True):
                analysis = query_decomposition_service.analyze_query(question, client=client, user_id=user_id)
                sub_qs = analysis.get("sub_questions", [question])
                q_type = analysis.get("type", "simple")
                is_multi_doc = analysis.get("is_multi_doc", False)
            else:
                sub_qs = [question]
                q_type = "simple"
                is_multi_doc = False
            decomp_ms = (time.time() - t_decomp_0) * 1000
            logger.info(f"[Stage: Decomposition] Query='{question}' -> type='{q_type}', sub_qs={sub_qs}, is_multi_doc={is_multi_doc} ({decomp_ms:.1f}ms)")

            # Stage 2: Hybrid Retrieval & Reranking per sub-question
            t_retrieval_0 = time.time()
            sub_reranked: List[Tuple[DocumentChunk, float]] = []

            for sub_q in sub_qs:
                # 1. Qdrant dense vector search
                dense_cands = vector_store.search(
                    query=sub_q,
                    user_id=user_id,
                    k=settings.RETRIEVE_K,
                    doc_filter=doc_filter,
                    document_id=document_id,
                    min_similarity=settings.MIN_SIMILARITY,
                    pipeline_version="v2"
                )

                # 2. Corpus-wide BM25 search with identical pre-filtering
                if getattr(settings, "ENABLE_HYBRID_BM25", True):
                    bm25_cands = corpus_bm25_index.search(
                        user_id=user_id,
                        query=sub_q,
                        k=settings.RETRIEVE_K,
                        doc_filter=doc_filter,
                        document_id=document_id,
                        pipeline_version="v2"
                    )
                    fused = compute_rrf_fusion(dense_cands, bm25_cands, k=60.0)
                else:
                    fused = dense_cands

                # 3. Cross-Encoder reranking per sub-question (with input length limit)
                if getattr(settings, "ENABLE_RERANKER", True) and fused:
                    reranked_pool = cross_encoder_reranker.rerank(
                        sub_q,
                        [c for c, _ in fused],
                        top_n=getattr(settings, "RERANK_TOP_N", 10)
                    )
                    sub_reranked.extend(reranked_pool)
                else:
                    sub_reranked.extend(fused[:getattr(settings, "RERANK_TOP_N", 10)])

            # Merge and deduplicate candidates across all sub-questions
            seen_cids: Set[str] = set()
            merged_candidates: List[Tuple[DocumentChunk, float]] = []
            for chunk, score in sub_reranked:
                if chunk.chunk_id not in seen_cids:
                    seen_cids.add(chunk.chunk_id)
                    merged_candidates.append((chunk, score))
            merged_candidates.sort(key=lambda x: x[1], reverse=True)

            # Deduplicate parents for small-to-big retrieval
            deduped_candidates = deduplicate_parents(merged_candidates)
            retrieval_ms = (time.time() - t_retrieval_0) * 1000
            logger.info(f"[Stage: Retrieval] Merged {len(deduped_candidates)} unique chunks across {len(sub_qs)} sub-questions ({retrieval_ms:.1f}ms)")

            if not deduped_candidates:
                logger.info(f"No candidates retrieved for question: '{question}'")
                return self._create_not_found_response(question, start_time)

            # Stage 3: Multi-Document Balance (guaranteed minimum per document)
            t_mmr_0 = time.time()
            is_comp_or_multi = (
                is_multi_doc
                or q_type in ("comparison", "multi_document")
                or any(term in question.lower() for term in ["compare", "versus", " vs ", "difference", "contrasting"])
            )
            if getattr(settings, "ENABLE_MULTI_DOC_BALANCE", True) and is_comp_or_multi:
                balanced = apply_multi_doc_balance(
                    deduped_candidates,
                    min_per_doc=getattr(settings, "MULTI_DOC_MIN_PER_DOC", 2),
                    top_n=settings.TOP_K_CHUNKS * 2
                )
            else:
                balanced = deduped_candidates

            # Stage 4: Post-Rerank MMR Diversity
            if getattr(settings, "ENABLE_DIVERSITY_MMR", True) and len(balanced) > settings.TOP_K_CHUNKS:
                final_chunks = apply_mmr_diversity(
                    balanced,
                    top_n=min(len(balanced), max(settings.TOP_K_CHUNKS, 8)),
                    lambda_param=0.7
                )
            else:
                final_chunks = balanced[:settings.TOP_K_CHUNKS]
            mmr_ms = (time.time() - t_mmr_0) * 1000

            retrieved_map = {chunk.chunk_id: (chunk, score) for chunk, score in final_chunks}
            retrieved_chunks = [chunk for chunk, _ in final_chunks]

            # Calculate qualitative retrieval strength
            top_score = final_chunks[0][1] if final_chunks else 0.0
            second_score = final_chunks[1][1] if len(final_chunks) > 1 else None
            retrieval_strength = compute_retrieval_strength(top_score, second_score)

            # Stage 5: Context Preparation with Parent-Child Resolution
            context_blocks = []
            for chunk, v_score in final_chunks:
                page_info = f"Page {chunk.page_start}" if chunk.page_start == chunk.page_end else f"Pages {chunk.page_start}-{chunk.page_end}"
                heading_info = f" | Section: {chunk.section_heading}" if chunk.section_heading else ""
                # Use parent section text if parent-child retrieval is enabled
                body_text = chunk.parent_text if (getattr(settings, "ENABLE_PARENT_CHILD", True) and chunk.parent_text) else chunk.text
                context_blocks.append(
                    f"[Chunk ID: {chunk.chunk_id} | Document: {chunk.document_name} | {page_info}{heading_info}]\n"
                    f"{body_text}"
                )
            context_text = "\n\n".join(context_blocks)

            # Stage 6: Generation Prompt
            t_gen_0 = time.time()
            system_prompt = (
                "You are an enterprise AI knowledge assistant. Answer the user's question "
                "strictly and factually based ONLY on the provided context excerpts.\n\n"
                "Rules:\n"
                "1. Answer ONLY using facts directly stated in the context excerpts. Do NOT extrapolate or assume.\n"
                "2. Cite the relevant chunk_id inline in brackets immediately following each fact, claim, or policy (e.g. '[chunk_id]').\n"
                "3. When answering comparison questions, YOU MUST USE A MARKDOWN TABLE comparing the items side-by-side across relevant criteria.\n"
                "4. When multiple sub-questions or distinct aspects are asked, answer each one explicitly using clear bullet points or section headings.\n"
                "5. If the context does not contain sufficient information to answer the question, state clearly: "
                "'Information regarding this topic was not found in the uploaded documents.'\n"
                "6. Preserve numbered lists, exact thresholds, and commands.\n"
                "7. Do NOT include meta-commentary, confidence scores, or certainty declarations (never write 'high confidence' or confidence metrics)."
            )

            user_prompt = f"Context Excerpts:\n{context_text}\n\nQuestion: {question}"

            create_kwargs = {
                "model": active_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": settings.LLM_TEMPERATURE if not is_reasoning_model(active_model) else None,
                "max_tokens": settings.LLM_MAX_TOKENS
            }
            if is_reasoning_model(active_model):
                create_kwargs["max_completion_tokens"] = settings.LLM_MAX_TOKENS

            answer_content = self._call_openai_with_retries(client, create_kwargs)
            gen_ms = (time.time() - t_gen_0) * 1000
            total_ms = (time.time() - start_time) * 1000
            logger.info(f"[Latency Breakdown] Decomp={decomp_ms:.1f}ms, Retrieval={retrieval_ms:.1f}ms, MMR={mmr_ms:.1f}ms, Gen={gen_ms:.1f}ms, Total={total_ms:.1f}ms")

            if not answer_content:
                return self._create_failure_response(
                    question=question,
                    start_time=start_time,
                    message="AI service encountered an error or timed out. Please try again later."
                )

            # Strict Citation Validation
            raw_cited_ids = extract_cited_chunk_ids(answer_content)
            valid_citations: List[CitationSource] = []
            valid_ids_seen = set()

            for cid in raw_cited_ids:
                if cid in retrieved_map and cid not in valid_ids_seen:
                    valid_ids_seen.add(cid)
                    chunk, v_score = retrieved_map[cid]
                    snippet = build_citation_snippet(
                        chunk_text=chunk.text,
                        question=question,
                        answer=answer_content,
                        max_chars=300
                    )
                    valid_citations.append(
                        CitationSource(
                            chunk_id=chunk.chunk_id,
                            source_name=chunk.document_name,
                            page_start=chunk.page_start,
                            page_end=chunk.page_end,
                            snippet=snippet,
                            score=round(v_score, 3),
                            id=len(valid_citations) + 1,
                            section_heading=chunk.section_heading
                        )
                    )

            is_insufficient = (
                answer_content.strip().lower().startswith("information regarding this topic was not found")
                or (
                    len(answer_content.strip()) < 180
                    and any(
                        term in answer_content.lower()
                        for term in [
                            "not found in the uploaded documents",
                            "does not contain sufficient information",
                            "cannot be determined from the excerpts",
                            "not mentioned in the provided context"
                        ]
                    )
                )
            )

            # If no inline citations but the model answered from context without declaring insufficient,
            # attribute citations to the top retrieved context chunks that match answer content
            if not valid_citations and not is_insufficient:
                for cid, (chunk, v_score) in list(retrieved_map.items())[:3]:
                    snippet = build_citation_snippet(
                        chunk_text=chunk.text,
                        question=question,
                        answer=answer_content,
                        max_chars=300
                    )
                    valid_citations.append(
                        CitationSource(
                            chunk_id=chunk.chunk_id,
                            source_name=chunk.document_name,
                            page_start=chunk.page_start,
                            page_end=chunk.page_end,
                            snippet=snippet,
                            score=round(v_score, 3),
                            id=len(valid_citations) + 1,
                            section_heading=chunk.section_heading
                        )
                    )

            if not valid_citations or is_insufficient:
                logger.info("No valid citations found in answer or answer declared insufficient. Setting answerable=False.")
                return self._create_not_found_response(question, start_time)

            # Parse lead and key bullet points
            lines = [l.strip() for l in answer_content.split("\n") if l.strip()]
            bullet_lines = [l for l in lines if l.startswith(("- ", "* ", "• "))]

            if bullet_lines:
                first_bullet_idx = next(i for i, l in enumerate(lines) if l.startswith(("- ", "* ", "• ")))
                lead_parts = lines[:first_bullet_idx]
                lead = " ".join(lead_parts) if lead_parts else lines[0]
                key_points = [re.sub(r"^[-*•]\s*", "", l).strip() for l in bullet_lines]
            else:
                lead = answer_content
                key_points = []

            clean_answer = strip_chunk_id_citations(answer_content)
            clean_lead = strip_chunk_id_citations(lead)
            clean_key_points = [strip_chunk_id_citations(kp) for kp in key_points if strip_chunk_id_citations(kp)]

            measured_time = f"{round(time.time() - start_time, 2)}s"

            return AskAIResponse(
                question=question,
                answer=clean_answer,
                citations=valid_citations,
                answerable=True,
                lead=clean_lead,
                key_points=clean_key_points,
                confidence=retrieval_strength,
                response_time=measured_time,
                sources_used=len(valid_citations),
                sources=valid_citations,
                retrieved_chunks=retrieved_chunks
            )
        except Exception as e:
            logger.error(f"OpenAI execution error: {e}", exc_info=True)
            return self._create_failure_response(
                question=question,
                start_time=start_time,
                message=f"AI service encountered an unhandled error ({type(e).__name__}): {e}"
            )

    def answer_query(
        self,
        question: str,
        user_id: str,
        doc_filter: Optional[List[str]] = None,
        document_id: Optional[str] = None,
        pipeline_version: Optional[str] = None
    ) -> AskAIResponse:
        """
        Public answer endpoint routing between legacy baseline ('v1')
        and improved pipeline ('v2') according to configuration or request parameter.
        Enforces tenant isolation by requiring verified caller user_id.
        """
        if not user_id or not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id is required to answer query")

        active_ver = pipeline_version or getattr(settings, "PIPELINE_VERSION", "v2")
        if active_ver == "v1":
            return self._answer_query_legacy(question, user_id=user_id, doc_filter=doc_filter, document_id=document_id)
        return self._answer_query_v2(question, user_id=user_id, doc_filter=doc_filter, document_id=document_id)


rag_service = RAGService()
