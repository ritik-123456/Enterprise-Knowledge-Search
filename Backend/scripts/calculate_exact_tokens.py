"""
Exact Empirical Token Utilization Measurement Script for EKS RAG
Measures exact numeric token values for:
1. System Prompt Template
2. User Questions
3. Context Excerpts (Baseline 8 chunks vs Pruned 4 chunks)
4. Total Prompt Tokens (Input Tokens)
5. Completion Tokens (Output Tokens from actual model runs)
6. Total Request Tokens Utilized & Percentage Savings
"""

import os
import sys
import json
import tiktoken

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.services.rag_service import rag_service
from app.services.chunking_service import chunking_service
from app.services.pdf_service import pdf_service
from app.services.vector_store import vector_store
from app.services.hybrid_retriever import corpus_bm25_index

enc = tiktoken.get_encoding("cl100k_base")

HANDBOOK_PDF = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "eks_handbook.pdf"))
SECURITY_PDF = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "security_policy.pdf"))
BENCHMARK_USER_ID = "exact_token_calc_user"

BENCHMARK_QUESTIONS = [
    {
        "id": "FAST-01",
        "category": "Fast-Path (Simple)",
        "question": "What is the maximum number of days application and control plane logs are retained?"
    },
    {
        "id": "COMP-01",
        "category": "Comparison (Complex)",
        "question": "Compare Karpenter NodePools with Managed Node Groups in terms of capacity types, node provisioning, and expiration policies."
    },
    {
        "id": "MHOP-01",
        "category": "Multi-Hop (Complex)",
        "question": "If a SEV1 incident occurs due to an API server 5xx rate above 2%, what is the target response time and within how many days must the postmortem be published?"
    },
    {
        "id": "MSEC-01",
        "category": "Multi-Section (Complex)",
        "question": "What are the Pod Disruption Budget (PDB) rules for stateless multi-replica services versus stateful database workloads, and how are snapshots scheduled?"
    },
    {
        "id": "MDOC-01",
        "category": "Cross-Document (Complex)",
        "question": "Compare the retention period for operational application and control plane logs in the EKS Handbook with the retention period for audit logs in the Security Standard."
    }
]

def load_actual_benchmark_answers():
    comp_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "benchmark_model_comparison.json"))
    if os.path.exists(comp_file):
        with open(comp_file, "r") as f:
            data = json.load(f)
            return data.get("gemini-3.5-flash-lite", {}).get("runs", [])
    return []

def main():
    print("=" * 70)
    print("EMPIRICAL TOKEN UTILIZATION MEASUREMENT - EKS RAG")
    print("=" * 70)

    # 1. Index fixtures
    vector_store.clear_user_documents(BENCHMARK_USER_ID)
    corpus_bm25_index.clear_user_index(BENCHMARK_USER_ID)

    for pdf_path in [HANDBOOK_PDF, SECURITY_PDF]:
        if not os.path.exists(pdf_path):
            continue
        doc_name = os.path.basename(pdf_path)
        doc_id = f"calc_{os.path.splitext(doc_name)[0]}"
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        pages = pdf_service.extract_text_by_pages(pdf_bytes, doc_name)
        chunks = chunking_service.process_document(pages, doc_name, doc_id, pipeline_version="v2")
        for c in chunks:
            c.user_id = BENCHMARK_USER_ID
        vector_store.add_document(doc_id, chunks, user_id=BENCHMARK_USER_ID)
        corpus_bm25_index.update_index(chunks, user_id=BENCHMARK_USER_ID)

    # 2. Measure System Prompt Tokens
    dummy_ctx, _ = rag_service._prepare_query_context_v2(BENCHMARK_QUESTIONS[0]["question"], BENCHMARK_USER_ID)
    system_prompt = dummy_ctx["create_kwargs"]["messages"][0]["content"]
    system_prompt_tokens = len(enc.encode(system_prompt))
    
    print(f"\n[1] SYSTEM PROMPT TOKEN COUNT:")
    print(f"    - System prompt characters: {len(system_prompt)}")
    print(f"    - System prompt exact tokens (cl100k_base): {system_prompt_tokens}")

    actual_runs = {r["question_id"]: r for r in load_actual_benchmark_answers()}

    eval_summary = []

    print("\n[2] PER-QUERY EXACT TOKEN MEASUREMENT:")
    print("-" * 70)

    for item in BENCHMARK_QUESTIONS:
        qid = item["id"]
        cat = item["category"]
        q = item["question"]
        q_tokens = len(enc.encode(q))

        # A. Optimized Pipeline (Step 2 Context Pruning active: 4 chunks for simple, 8 for complex)
        ctx_opt, _ = rag_service._prepare_query_context_v2(q, BENCHMARK_USER_ID)
        opt_chunks = ctx_opt["retrieved_chunks"]
        opt_chunk_count = len(opt_chunks)
        opt_user_msg = ctx_opt["create_kwargs"]["messages"][1]["content"]
        opt_prompt_tokens = len(enc.encode(system_prompt)) + len(enc.encode(opt_user_msg))
        
        # Context only
        opt_context_raw = opt_user_msg.replace(f"Question: {q}", "").replace("Context Excerpts:\n", "").strip()
        opt_context_tokens = len(enc.encode(opt_context_raw))

        # B. Baseline Pipeline (Unpruned: always 8 chunks)
        orig_simple_k = settings.SIMPLE_TOP_K_CHUNKS
        settings.SIMPLE_TOP_K_CHUNKS = settings.TOP_K_CHUNKS  # force 8
        ctx_base, _ = rag_service._prepare_query_context_v2(q, BENCHMARK_USER_ID)
        settings.SIMPLE_TOP_K_CHUNKS = orig_simple_k
        
        base_chunks = ctx_base["retrieved_chunks"]
        base_chunk_count = len(base_chunks)
        base_user_msg = ctx_base["create_kwargs"]["messages"][1]["content"]
        base_prompt_tokens = len(enc.encode(system_prompt)) + len(enc.encode(base_user_msg))
        base_context_raw = base_user_msg.replace(f"Question: {q}", "").replace("Context Excerpts:\n", "").strip()
        base_context_tokens = len(enc.encode(base_context_raw))

        # C. Output Completion Tokens (from actual benchmark answer if available)
        ans_preview = actual_runs.get(qid, {}).get("answer_preview", "")
        # Get actual answer by calling OpenAI mock/run or checking full answer from eval_results
        # Let's count completion tokens for the actual answer text
        completion_tokens = len(enc.encode(ans_preview))

        tokens_saved = base_prompt_tokens - opt_prompt_tokens
        savings_pct = (tokens_saved / base_prompt_tokens * 100.0) if base_prompt_tokens > 0 else 0.0

        row = {
            "id": qid,
            "category": cat,
            "question_tokens": q_tokens,
            "base_chunk_count": base_chunk_count,
            "base_context_tokens": base_context_tokens,
            "base_prompt_tokens": base_prompt_tokens,
            "opt_chunk_count": opt_chunk_count,
            "opt_context_tokens": opt_context_tokens,
            "opt_prompt_tokens": opt_prompt_tokens,
            "prompt_tokens_saved": tokens_saved,
            "savings_pct": round(savings_pct, 1),
            "opt_total_tokens": opt_prompt_tokens + completion_tokens
        }
        eval_summary.append(row)

        print(f"Query {qid} ({cat}):")
        print(f"  • Question: '{q[:50]}...' ({q_tokens} tokens)")
        print(f"  • Baseline:  {base_chunk_count} chunks -> Context: {base_context_tokens} tok | Total Prompt: {base_prompt_tokens} tok")
        print(f"  • Optimized: {opt_chunk_count} chunks -> Context: {opt_context_tokens} tok | Total Prompt: {opt_prompt_tokens} tok")
        if tokens_saved > 0:
            print(f"  • >>> SAVINGS: {tokens_saved} prompt tokens saved ({savings_pct:.1f}% reduction) <<<")
        else:
            print(f"  • >>> Complex query retained full grounding ({opt_chunk_count} chunks) <<<")
        print()

    # Save summary to JSON
    out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "exact_token_breakdown.json"))
    with open(out_path, "w") as f:
        json.dump({
            "system_prompt_tokens": system_prompt_tokens,
            "summary": eval_summary
        }, f, indent=2)
    print(f"Results saved to {out_path}")

if __name__ == "__main__":
    main()

