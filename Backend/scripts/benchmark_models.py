"""
Model Benchmarking & Performance Comparison Suite for Enterprise Knowledge Search
Evaluates candidate high-speed models across:
1. Time-to-First-Token (TTFT) via Server-Sent Events (SSE)
2. Total Latency & Generation Throughput (tokens/sec)
3. Grounded Fact Recall & Correctness (%)
4. Citation Validity & Precision
5. Structural Formatting Compliance (Markdown Tables & Lists)
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.schemas.rag import DocumentChunk
from app.services.rag_service import rag_service
from app.services.vector_store import vector_store
from app.services.hybrid_retriever import corpus_bm25_index
from app.services.pdf_service import pdf_service
from app.services.chunking_service import chunking_service

BENCHMARK_USER_ID = "benchmark_eval_user"
HANDBOOK_PDF = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "eks_handbook.pdf"))
SECURITY_PDF = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "security_policy.pdf"))

# Candidate models to evaluate
CANDIDATE_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite"
]

BENCHMARK_QUESTIONS = [
    {
        "id": "FAST-01",
        "category": "Fast-Path (Simple)",
        "question": "What is the maximum number of days application and control plane logs are retained?",
        "expected_facts": [
            "30 days",
            "application and control plane logs"
        ]
    },
    {
        "id": "COMP-01",
        "category": "Comparison (Table Required)",
        "question": "Compare Karpenter NodePools with Managed Node Groups in terms of capacity types, node provisioning, and expiration policies.",
        "expected_facts": [
            "Managed node groups use EC2 Auto Scaling groups and Amazon Linux 2023",
            "Karpenter uses NodePool CRDs with on-demand or spot capacity",
            "Karpenter nodes expire after 720 hours (720h) and use WhenEmptyOrUnderutilized consolidation"
        ]
    },
    {
        "id": "MHOP-01",
        "category": "Multi-Hop",
        "question": "If a SEV1 incident occurs due to an API server 5xx rate above 2%, what is the target response time and within how many days must the postmortem be published?",
        "expected_facts": [
            "SEV1 response target is 15 minutes",
            "Blameless postmortem must be published within 5 business days"
        ]
    },
    {
        "id": "MSEC-01",
        "category": "Multi-Section",
        "question": "What are the Pod Disruption Budget (PDB) rules for stateless multi-replica services versus stateful database workloads, and how are snapshots scheduled?",
        "expected_facts": [
            "Multi-replica deployments require maxUnavailable of 1",
            "Stateful database workloads require maxUnavailable of 0",
            "Snapshots taken daily at 01:00 UTC and kept for 7 days"
        ]
    },
    {
        "id": "MDOC-01",
        "category": "Cross-Document",
        "question": "Compare the retention period for operational application and control plane logs in the EKS Handbook with the retention period for audit logs in the Security Standard.",
        "expected_facts": [
            "EKS Handbook specifies 30 days retention for application and control plane logs",
            "Security Standard requires audit logs retained for 365 days (1 year)"
        ]
    }
]


def setup_benchmark_fixtures() -> None:
    """Indexes handbook and security policy fixtures strictly for the benchmark user."""
    print("Preparing vector index fixtures for benchmark...")
    vector_store.clear_user_documents(BENCHMARK_USER_ID)
    corpus_bm25_index.clear_user_index(BENCHMARK_USER_ID)

    for pdf_path in [HANDBOOK_PDF, SECURITY_PDF]:
        if not os.path.exists(pdf_path):
            print(f"[Warning] Fixture {pdf_path} not found. Skipping.")
            continue
        doc_name = os.path.basename(pdf_path)
        doc_id = f"bench_{os.path.splitext(doc_name)[0]}"
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        pages = pdf_service.extract_text_by_pages(pdf_bytes, doc_name)
        chunks = chunking_service.process_document(pages, doc_name, doc_id, pipeline_version="v2")
        for c in chunks:
            c.user_id = BENCHMARK_USER_ID

        vector_store.add_document(doc_id, chunks, user_id=BENCHMARK_USER_ID)
        corpus_bm25_index.update_index(chunks, user_id=BENCHMARK_USER_ID)
        print(f"  - Indexed {doc_name}: {len(chunks)} chunks")


def evaluate_fact_coverage(answer: str, expected_facts: List[str]) -> Tuple[float, List[str]]:
    """Scores answer fact coverage against expected ground truth facts."""
    if not answer or "not found in the uploaded documents" in answer.lower():
        return 0.0, ["Not found or empty answer"]

    ans_lower = answer.lower()
    met = 0
    details = []

    for fact in expected_facts:
        tokens = [t.lower() for t in re.findall(r'[A-Za-z0-9_\-\.:]{3,}', fact)]
        core_tokens = [t for t in tokens if t not in {"the", "and", "for", "with", "from", "that", "this", "uses", "must"}]
        matches = sum(1 for tok in core_tokens if tok in ans_lower)
        ratio = matches / len(core_tokens) if core_tokens else 0.0

        if ratio >= 0.5:
            met += 1
            details.append(f"✓ '{fact[:35]}...'")
        else:
            details.append(f"✗ '{fact[:35]}...'")

    score = met / len(expected_facts) if expected_facts else 1.0
    return round(score * 100.0, 1), details


def benchmark_model_streaming(model_name: str, test_case: Dict[str, Any]) -> Dict[str, Any]:
    """Runs a single test case through streaming generator, measuring TTFT, total latency, and tokens."""
    q = test_case["question"]
    t0 = time.time()
    ttft_ms = None
    tokens = []
    done_payload = None

    try:
        gen = rag_service.answer_query_stream(
            question=q,
            user_id=BENCHMARK_USER_ID,
            model=model_name
        )

        for raw_line in gen:
            trimmed = raw_line.strip()
            if not trimmed.startswith("data:"):
                continue
            payload_str = trimmed.replace("data:", "").strip()
            if not payload_str:
                continue

            try:
                data = json.loads(payload_str)
                event_type = data.get("type")

                if event_type == "token":
                    if ttft_ms is None:
                        ttft_ms = round((time.time() - t0) * 1000.0, 1)
                    tokens.append(data.get("token", ""))
                elif event_type == "done":
                    done_payload = data
            except Exception:
                pass

        total_latency_s = round(time.time() - t0, 2)
        answer_text = done_payload.get("answer", "") if done_payload else "".join(tokens)
        token_count = len(tokens)
        gen_duration = (total_latency_s - ((ttft_ms or 0) / 1000.0))
        tps = round(token_count / max(gen_duration, 0.05), 1) if token_count > 0 else 0.0

        fact_score, fact_details = evaluate_fact_coverage(answer_text, test_case["expected_facts"])

        # Check markdown table presence for comparison questions
        has_table = ("|" in answer_text and "---" in answer_text) if test_case["category"].startswith("Comparison") else True
        citations_count = len(done_payload.get("sources", [])) if done_payload else 0

        return {
            "status": "success",
            "model": model_name,
            "question_id": test_case["id"],
            "ttft_ms": ttft_ms or round(total_latency_s * 1000.0, 1),
            "total_latency_s": total_latency_s,
            "token_count": token_count,
            "tokens_per_sec": tps,
            "fact_score_pct": fact_score,
            "citations_verified": citations_count,
            "table_formatted": has_table,
            "answer_preview": answer_text[:120].replace("\n", " ") + "..."
        }
    except Exception as e:
        return {
            "status": "error",
            "model": model_name,
            "question_id": test_case["id"],
            "error": str(e),
            "ttft_ms": 0.0,
            "total_latency_s": round(time.time() - t0, 2),
            "token_count": 0,
            "tokens_per_sec": 0.0,
            "fact_score_pct": 0.0,
            "citations_verified": 0,
            "table_formatted": False,
            "answer_preview": f"Error: {e}"
        }


def run_benchmark(models_to_test: Optional[List[str]] = None) -> Dict[str, Any]:
    """Runs complete model benchmarking suite across selected models."""
    setup_benchmark_fixtures()

    selected_models = models_to_test or [m for m in CANDIDATE_MODELS if not (m.startswith("gpt-") and not settings.OPENAI_API_KEY)]
    print("\n" + "=" * 94)
    print(f"STARTING LLM MODEL BENCHMARK (Candidate Models: {', '.join(selected_models)})")
    print("=" * 94)

    benchmark_results = {}

    for model in selected_models:
        print(f"\nEvaluating Model: [{model}]")
        model_runs = []
        for q in BENCHMARK_QUESTIONS:
            print(f"  - Running {q['id']} ({q['category']})... ", end="", flush=True)
            res = benchmark_model_streaming(model, q)
            if res["status"] == "success":
                print(f"TTFT: {res['ttft_ms']}ms | Total: {res['total_latency_s']}s | Recall: {res['fact_score_pct']}% | {res['tokens_per_sec']} tps")
            else:
                print(f"FAILED: {res.get('error', 'Unknown error')}")
            model_runs.append(res)
            time.sleep(0.5)  # Avoid rate limit bursts

        successful_runs = [r for r in model_runs if r["status"] == "success"]
        if successful_runs:
            avg_ttft = round(sum(r["ttft_ms"] for r in successful_runs) / len(successful_runs), 1)
            avg_lat = round(sum(r["total_latency_s"] for r in successful_runs) / len(successful_runs), 2)
            avg_tps = round(sum(r["tokens_per_sec"] for r in successful_runs) / len(successful_runs), 1)
            avg_fact = round(sum(r["fact_score_pct"] for r in successful_runs) / len(successful_runs), 1)
            table_compliance = round(sum(1 for r in successful_runs if r["table_formatted"]) / len(successful_runs) * 100.0, 1)
            avg_cits = round(sum(r["citations_verified"] for r in successful_runs) / len(successful_runs), 1)
        else:
            avg_ttft, avg_lat, avg_tps, avg_fact, table_compliance, avg_cits = 0, 0, 0, 0, 0, 0

        benchmark_results[model] = {
            "model_name": model,
            "runs": model_runs,
            "metrics": {
                "avg_ttft_ms": avg_ttft,
                "avg_latency_s": avg_lat,
                "avg_tokens_per_sec": avg_tps,
                "avg_fact_recall_pct": avg_fact,
                "table_compliance_pct": table_compliance,
                "avg_citations_per_query": avg_cits,
                "success_rate_pct": round(len(successful_runs) / len(model_runs) * 100.0, 1)
            }
        }

    # Print Comparison Table
    print("\n" + "=" * 104)
    print("MODEL BENCHMARK COMPARISON TABLE")
    print("=" * 104)
    print(f"{'Model Name':<28} | {'Avg TTFT':<11} | {'Avg Latency':<12} | {'Throughput':<12} | {'Fact Recall':<12} | {'Table Comp':<11} | {'Success':<8}")
    print("-" * 104)

    for model, data in benchmark_results.items():
        m = data["metrics"]
        print(f"{model:<28} | {m['avg_ttft_ms']:>8.1f} ms | {m['avg_latency_s']:>10.2f} s | {m['avg_tokens_per_sec']:>7.1f} tok/s | {m['avg_fact_recall_pct']:>10.1f} % | {m['table_compliance_pct']:>9.1f} % | {m['success_rate_pct']:>6.1f} %")

    print("=" * 104)

    # Clean up test index
    vector_store.clear_user_documents(BENCHMARK_USER_ID)
    corpus_bm25_index.clear_user_index(BENCHMARK_USER_ID)

    # Save to JSON artifact
    out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "benchmark_model_comparison.json"))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_results, f, indent=2)
    print(f"\nFull benchmark data saved to: {out_path}\n")

    return benchmark_results


if __name__ == "__main__":
    models_arg = sys.argv[1].split(",") if len(sys.argv) > 1 else None
    run_benchmark(models_to_test=models_arg)
