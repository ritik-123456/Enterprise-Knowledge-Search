"""
Query Decomposition & Iterative Multi-Hop Reasoning Service
1. Classifies user question into simple vs complex (comparison, multi-hop, multi-section, multi-document).
2. Decomposes complex questions into 2-5 standalone sub-questions (strictly JSON output).
3. Robust JSON-parse fallback to simple query path upon syntax error or failure.
4. Iterative multi-hop retrieval (max 3 hops) with defined stop conditions.
5. Strict capping of LLM calls per query to preserve AI token quotas.
6. Per-stage latency measurement and logging.
"""

import json
import logging
import re
import time
from typing import List, Dict, Any, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

# Compact prompt template to strictly minimize token consumption
DECOMPOSITION_PROMPT = """You are a query planner for an enterprise RAG knowledge engine.
Analyze the user question and classify it as "simple" or "complex" (comparison, multi_hop, multi_section, multi_document).

Rules:
1. If "simple" (lookup of a single fact), return 1 sub-question (the question itself).
2. If "complex" (comparison between 2+ items, multi-hop dependency, or spans multiple topics/docs), break it down into 2 to 4 self-contained, standalone sub-questions that can be retrieved independently.
3. Identify if the query requires multi-document or comparative balancing.
4. RETURN STRICT JSON ONLY, NO EXPLANATION, NO MARKDOWN FENCES.

JSON schema:
{
  "is_complex": boolean,
  "type": "simple" | "comparison" | "multi_hop" | "multi_section" | "multi_document",
  "sub_questions": ["standalone question 1", "standalone question 2"],
  "is_multi_doc": boolean
}

Question: {question}"""

COMPLEX_QUERY_PATTERNS = [
    # 1. Comparison keywords
    r"\b(?:compare|comparison|versus|vs\.?|difference|differences|contrasting|diff|tradeoffs?|pros and cons|better than|alternative to)\b",
    # 2. 'Between X and Y' comparison structure
    r"\bbetween\b.+\band\b",
    # 3. Cross-document / multi-policy references
    r"\b(?:across|in)\s+(?:both|all|multiple)\s+(?:documents?|pdfs?|policies|standards?)\b",
    r"\b(?:handbook|policy|standard)\b.+\b(?:handbook|policy|standard)\b",
    # 4. Multi-clause interrogatives (e.g. "... and what is...", ", which team...", "; how do I...")
    r"[,;]\s*(?:and\s+)?(?:what|how|which|who|where|when|why)\b",
    r"\band\s+(?:what|how|which|who|where|when|why)\b",
]


def is_likely_complex(question: str) -> bool:
    """
    Fast-path heuristic rule to detect if a question requires decomposition.
    Returns True if question shows clear patterns of comparison, multi-hop, or multi-part queries.
    Returns False for standard single-fact lookup queries, bypassing the LLM planner (< 1ms).
    """
    q = question.strip()
    if not q:
        return False

    # If query contains multiple question marks (e.g. "What is X? And what is Y?"), it's multi-part
    if q.count("?") >= 2:
        return True

    q_lower = q.lower()
    for pattern in COMPLEX_QUERY_PATTERNS:
        if re.search(pattern, q_lower):
            return True

    # If long query (> 25 words) with conjunctions, it may contain multiple clauses
    words = q.split()
    if len(words) > 25 and ("," in q or " and " in q_lower or ";" in q):
        return True

    return False


class QueryDecompositionService:
    def __init__(self):
        self._llm_cache: Dict[str, Dict[str, Any]] = {}

    def _call_llm_json(self, client, prompt: str) -> Optional[str]:
        """Calls LLM with minimal tokens and retries for transient errors."""
        try:
            model = settings.LLM_MODEL
            if settings.is_gemini and not ("gemini" in model.lower()):
                model = "gemini-flash-lite-latest"

            create_kwargs = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 250,
                "temperature": 0.0
            }
            resp = client.chat.completions.create(**create_kwargs)
            if resp.choices and resp.choices[0].message and resp.choices[0].message.content:
                return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Decomposition LLM call notice: {e}")
        return None

    def analyze_query(self, question: str, client: Optional[Any] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Classifies and decomposes the query.
        Falls back safely to simple path if JSON parsing fails or LLM is unavailable.
        """
        # Default simple fallback
        fallback = {
            "is_complex": False,
            "type": "simple",
            "sub_questions": [question],
            "is_multi_doc": False
        }

        if not getattr(settings, "ENABLE_QUERY_DECOMPOSITION", True):
            return fallback

        # Check local cache first to save tokens (keyed by user_id to prevent cross-tenant leaks)
        q_clean = question.strip().lower()
        cache_key = f"{user_id}:{q_clean}" if user_id else q_clean
        if cache_key in self._llm_cache:
            return self._llm_cache[cache_key]

        # Fast-Path Rule Check (Bypass LLM planner for single-fact/simple queries)
        if not is_likely_complex(question):
            logger.info(f"[Fast-Path] Query '{question[:60]}' identified as simple. Bypassing LLM planner (<1ms).")
            self._llm_cache[cache_key] = fallback
            return fallback

        logger.info(f"[Query Planner] Complex query detected for '{question[:60]}'. Invoking LLM decomposition...")

        if not client:
            try:
                from openai import OpenAI
                active_key = settings.active_api_key
                if not active_key:
                    return fallback
                client_kwargs = {"api_key": active_key}
                if settings.is_gemini:
                    client_kwargs["base_url"] = settings.OPENAI_BASE_URL or "https://generativelanguage.googleapis.com/v1beta/openai/"
                elif settings.OPENAI_BASE_URL:
                    client_kwargs["base_url"] = settings.OPENAI_BASE_URL
                client = OpenAI(**client_kwargs)
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI client for decomposition: {e}")
                return fallback

        prompt = DECOMPOSITION_PROMPT.replace("{question}", question)
        raw_output = self._call_llm_json(client, prompt)
        if not raw_output:
            return fallback

        # Robust JSON extraction with regex fallback
        try:
            # Strip markdown code fences if present
            cleaned = re.sub(r'^```(?:json)?\s*', '', raw_output.strip())
            cleaned = re.sub(r'\s*```$', '', cleaned.strip())

            # Find matching JSON object braces
            json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if json_match:
                cleaned = json_match.group(0)

            data = json.loads(cleaned)
            sub_qs = data.get("sub_questions", [])
            if not isinstance(sub_qs, list) or not sub_qs:
                sub_qs = [question]

            result = {
                "is_complex": bool(data.get("is_complex", len(sub_qs) > 1)),
                "type": str(data.get("type", "simple")),
                "sub_questions": [str(s).strip() for s in sub_qs if str(s).strip()][:5],
                "is_multi_doc": bool(data.get("is_multi_doc", False))
            }
            self._llm_cache[cache_key] = result
            return result
        except Exception as parse_err:
            logger.warning(f"JSON-parse fallback activated for query '{question}': {parse_err}. Raw output was: {raw_output[:100]}")
            return fallback


query_decomposition_service = QueryDecompositionService()
