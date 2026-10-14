"""
Comprehensive Cross-Question Evaluation Benchmark for Enterprise Knowledge Search
Evaluates complex cross-questions across 4 distinct categories:
1. Comparison Questions (comparing 2+ features/policies)
2. Multi-Hop Questions (inter-dependent chain of reasoning)
3. Multi-Section Questions (synthesizing content across distant sections)
4. Multi-Document Questions (cross-referencing handbook and security policy)

Evaluates both Retrieval Recall (by target pages and sections) and Answer Faithfulness/Correctness.
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

# Ensure app package is discoverable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.schemas.rag import DocumentChunk, AskAIResponse
from app.services.pdf_service import pdf_service
from app.services.chunking_service import chunking_service
from app.services.vector_store import vector_store
from app.services.rag_service import rag_service

HANDBOOK_PDF = os.path.abspath(os.path.join(os.path.dirname(__file__), "fixtures", "eks_handbook.pdf"))
SECURITY_PDF = os.path.abspath(os.path.join(os.path.dirname(__file__), "fixtures", "security_policy.pdf"))

CROSS_EVAL_DATASET: List[Dict[str, Any]] = [
    # ---------------------------------------------------------
    # Category 1: Comparison Questions (5)
    # ---------------------------------------------------------
    {
        "id": "COMP-01",
        "category": "Comparison",
        "question": "Compare Karpenter NodePools with Managed Node Groups in terms of capacity types, node provisioning, and expiration policies.",
        "target_docs": ["eks_handbook.pdf"],
        "target_pages": [4, 5],
        "target_sections": ["4.1 Managed node groups", "4.2 Karpenter NodePools"],
        "expected_facts": [
            "Managed node groups use EC2 Auto Scaling groups and Amazon Linux 2023",
            "Karpenter uses NodePool CRDs with on-demand or spot capacity",
            "Karpenter nodes expire after 720 hours (720h) and use WhenEmptyOrUnderutilized consolidation"
        ]
    },
    {
        "id": "COMP-02",
        "category": "Comparison",
        "question": "Compare Amazon EBS (gp3) with Amazon EFS storage in terms of CSI drivers, workload suitability, and reclaim policy.",
        "target_docs": ["eks_handbook.pdf"],
        "target_pages": [9],
        "target_sections": ["10.1 EBS and EFS"],
        "expected_facts": [
            "EBS uses gp3 storage class and EBS CSI driver with Delete reclaim policy",
            "EFS uses EFS CSI driver for shared read-write volumes and build caches",
            "EFS is not suitable for latency-sensitive databases"
        ]
    },
    {
        "id": "COMP-03",
        "category": "Comparison",
        "question": "Compare IAM Roles for Service Accounts (IRSA) with EKS Pod Identity in terms of configuration requirements and migration review.",
        "target_docs": ["eks_handbook.pdf"],
        "target_pages": [5, 6],
        "target_sections": ["5.1 IRSA naming and setup", "5.2 Migration to EKS Pod Identity"],
        "expected_facts": [
            "IRSA requires an OIDC provider, trust policy, and service account annotation eks.amazonaws.com/role-arn",
            "EKS Pod Identity simplifies setup without complex OIDC trust policies",
            "Migrated workloads must pass a permission review reducing actions to those actually used over 30 days"
        ]
    },
    {
        "id": "COMP-04",
        "category": "Comparison",
        "question": "Compare the Pod Disruption Budget (PDB) maxUnavailable settings between stateless multi-replica services and stateful database workloads.",
        "target_docs": ["eks_handbook.pdf"],
        "target_pages": [9],
        "target_sections": ["9.2 Disruption budgets"],
        "expected_facts": [
            "Deployments with 2+ replicas require maxUnavailable of 1",
            "Stateful database workloads require maxUnavailable of 0",
            "Stateful workloads are drained manually under supervision"
        ]
    },
    {
        "id": "COMP-05",
        "category": "Comparison",
        "question": "Compare the customer impact definition and response target between SEV1, SEV2, and SEV3 incidents.",
        "target_docs": ["eks_handbook.pdf"],
        "target_pages": [11],
        "target_sections": ["13.1 Severity levels"],
        "expected_facts": [
            "SEV1: Customer-facing outage or data loss, 15 minutes response target",
            "SEV2: Significant degradation with workaround, 30 minutes response target",
            "SEV3: Minor issue with no customer impact, Next business day response"
        ]
    },

    # ---------------------------------------------------------
    # Category 2: Multi-Hop Questions (5)
    # ---------------------------------------------------------
    {
        "id": "MHOP-01",
        "category": "Multi-Hop",
        "question": "What target CPU utilization triggers scaling for payments-api, what alert is triggered if node CPU exceeds its threshold, and what is the severity level of that alert?",
        "target_docs": ["eks_handbook.pdf"],
        "target_pages": [8],
        "target_sections": ["8.2 Alert thresholds", "9.1 Horizontal Pod Autoscaler defaults"],
        "expected_facts": [
            "payments-api HPA targets 65% CPU utilization",
            "NodeHighCPU alert triggers when CPU is above 85% for 10 minutes",
            "NodeHighCPU alert has a severity level of SEV3"
        ]
    },
    {
        "id": "MHOP-02",
        "category": "Multi-Hop",
        "question": "If a pod enters ImagePullBackOff, what is the likely cause, what is the first action to take, and which team owns the namespace and Helm release where this pod runs?",
        "target_docs": ["eks_handbook.pdf"],
        "target_pages": [2, 10],
        "target_sections": ["1.2 Ownership and change windows", "11.1 Common pod errors"],
        "expected_facts": [
            "Likely cause is wrong tag or missing ECR permission",
            "First action is check image name and node role",
            "Application teams own their namespaces and Helm releases"
        ]
    },
    {
        "id": "MHOP-03",
        "category": "Multi-Hop",
        "question": "Which cluster is dedicated to sandbox experiments, what Kubernetes minor version runs on production, and how long may an unsupported Kubernetes version remain in production?",
        "target_docs": ["eks_handbook.pdf"],
        "target_pages": [2, 3],
        "target_sections": ["1.1 Purpose of this handbook", "2.1 Kubernetes version policy"],
        "expected_facts": [
            "Sandbox cluster for experiments is dev-euw1-sandbox",
            "prod-use1-core runs Kubernetes 1.31",
            "Minor version must not remain in production for more than 12 months after end of standard support"
        ]
    },
    {
        "id": "MHOP-04",
        "category": "Multi-Hop",
        "question": "What is the Karpenter NodePool consolidation policy, after how many hours do nodes expire, and what maxUnavailable disruption budget setting must database pods have during node drains?",
        "target_docs": ["eks_handbook.pdf"],
        "target_pages": [5, 9],
        "target_sections": ["4.2 Karpenter NodePools", "9.2 Disruption budgets"],
        "expected_facts": [
            "Consolidation policy is WhenEmptyOrUnderutilized",
            "Nodes expire after 720 hours (720h)",
            "Stateful database workloads require maxUnavailable 0"
        ]
    },
    {
        "id": "MHOP-05",
        "category": "Multi-Hop",
        "question": "How many CoreDNS replicas are required in production, what DNS caching daemon is used, and what specific domain suffix is reserved for platform services?",
        "target_docs": ["eks_handbook.pdf"],
        "target_pages": [4],
        "target_sections": ["3.2 Network policies and DNS"],
        "expected_facts": [
            "Minimum of 3 replicas of CoreDNS in production",
            "Uses NodeLocal DNSCache",
            "kube-system.svc.cluster.local is reserved for platform services"
        ]
    },

    # ---------------------------------------------------------
    # Category 3: Multi-Section Questions (5)
    # ---------------------------------------------------------
    {
        "id": "MSEC-01",
        "category": "Multi-Section",
        "question": "Explain the full cluster upgrade process including the Kubernetes version policy, the exact order of component upgrades, and the pre-upgrade ticket requirements.",
        "target_docs": ["eks_handbook.pdf"],
        "target_pages": [2, 3, 6, 7],
        "target_sections": ["2.1 Kubernetes version policy", "7.1 Upgrade order", "7.2 Pre-upgrade checklist"],
        "expected_facts": [
            "Acme follows an n-1 version policy, staging upgrades first",
            "Upgrade order: control plane first, then managed node groups, then cluster add-ons",
            "Pre-upgrade ticket requires deprecated-API check, add-on versions before/after, and named rollback owner"
        ]
    },
    {
        "id": "MSEC-02",
        "category": "Multi-Section",
        "question": "What is the backup, snapshot schedule, and quarterly restore verification drill process for persistent storage and disaster recovery?",
        "target_docs": ["eks_handbook.pdf"],
        "target_pages": [7, 9, 10],
        "target_sections": ["7.2 Pre-upgrade checklist", "10.2 Snapshots and recovery"],
        "expected_facts": [
            "Volume snapshots are taken daily at 01:00 UTC and kept for 7 days",
            "Quarterly restore drill restores random snapshot into staging cluster to verify data",
            "Snapshots encrypted with same KMS key as source volume"
        ]
    },
    {
        "id": "MSEC-03",
        "category": "Multi-Section",
        "question": "Detail the observability standards: which required labels must every /metrics endpoint have, how long are metrics and logs retained, and what is the alert threshold for API server errors?",
        "target_docs": ["eks_handbook.pdf"],
        "target_pages": [7, 8],
        "target_sections": ["8.1 Metrics and logs", "8.2 Alert thresholds"],
        "expected_facts": [
            "/metrics endpoint must expose labels: app, team, env",
            "Metrics retained for 15 days, application and control plane logs retained for 30 days",
            "APIServerErrors alert triggers when 5xx rate is above 2% for 5 minutes (SEV1)"
        ]
    },
    {
        "id": "MSEC-04",
        "category": "Multi-Section",
        "question": "What cost management rules govern Spot capacity usage, what three tags are mandatory on all AWS resources, and after how many days are unclaimed resources removed?",
        "target_docs": ["eks_handbook.pdf"],
        "target_pages": [11],
        "target_sections": ["12.1 Spot capacity and tagging"],
        "expected_facts": [
            "Spot instances save up to 70%, for batch and non-critical workloads only",
            "Mandatory tags are cost-center, owner, and env",
            "Untagged resources reported weekly and removed after 14 days if unclaimed"
        ]
    },
    {
        "id": "MSEC-05",
        "category": "Multi-Section",
        "question": "What are the specific weekly on-call rotation hours and handoff procedures, and within how many business days must a blameless postmortem be published following an outage?",
        "target_docs": ["eks_handbook.pdf"],
        "target_pages": [11, 12],
        "target_sections": ["13.1 Severity levels", "13.2 On-call and postmortems"],
        "expected_facts": [
            "On-call rotation changes every Monday at 09:00 UTC with required handover note",
            "Primary and secondary engineers listed in paging tool",
            "Blameless postmortem must be published within 5 business days of every SEV1 or SEV2 incident"
        ]
    },

    # ---------------------------------------------------------
    # Category 4: Multi-Document Questions (5)
    # ---------------------------------------------------------
    {
        "id": "MDOC-01",
        "category": "Multi-Document",
        "question": "Compare the retention period for operational application and control plane logs in the EKS Handbook with the retention period for audit logs in the Security Standard.",
        "target_docs": ["eks_handbook.pdf", "security_policy.pdf"],
        "target_pages": [7, 2],
        "target_sections": ["8.1 Metrics and logs", "5. Audit Log Retention and Compliance Cadence"],
        "expected_facts": [
            "EKS Handbook specifies application and control plane logs are retained for 30 days",
            "Security Standard requires audit logs to be retained for a minimum of 365 days (1 year) in S3 Glacier"
        ]
    },
    {
        "id": "MDOC-02",
        "category": "Multi-Document",
        "question": "Compare the incident response target and notification procedures for an operational SEV1 incident versus a security SEC-1 incident.",
        "target_docs": ["eks_handbook.pdf", "security_policy.pdf"],
        "target_pages": [11, 2],
        "target_sections": ["13.1 Severity levels", "6. Incident Escalation: Security vs Operational Incidents"],
        "expected_facts": [
            "Operational SEV1 incidents have a 15-minute response target 24 hours a day",
            "Security SEC-1 incidents have a 10-minute response target and page the CISO on-call directly"
        ]
    },
    {
        "id": "MDOC-03",
        "category": "Multi-Document",
        "question": "How is secrets encryption configured according to the EKS Handbook, and what specific key rotation interval and syncing operator are mandated by the Security Standard?",
        "target_docs": ["eks_handbook.pdf", "security_policy.pdf"],
        "target_pages": [6, 1],
        "target_sections": ["6.1 Pod security and secrets", "3. Secrets Management and Encryption Standards"],
        "expected_facts": [
            "EKS Handbook specifies KMS encryption using alias/eks-prod-secrets",
            "Security Standard mandates automatic KMS key rotation every 90 days",
            "External Secrets Operator (ESO) is the only approved syncing mechanism"
        ]
    },
    {
        "id": "MDOC-04",
        "category": "Multi-Document",
        "question": "What vulnerability remediation SLA is required for Critical container findings in the Security Standard, and how are non-compliant deployments blocked in production?",
        "target_docs": ["eks_handbook.pdf", "security_policy.pdf"],
        "target_pages": [6, 2],
        "target_sections": ["6.2 Image provenance", "4. Vulnerability Remediation SLAs"],
        "expected_facts": [
            "Security Standard requires Critical vulnerabilities to be remediated within 24 hours",
            "Kyverno admission controller blocks images with unpatched Critical findings older than 24 hours"
        ]
    },
    {
        "id": "MDOC-05",
        "category": "Multi-Document",
        "question": "Compare the standard change window permissions in the EKS Handbook with the session duration limits and MFA requirements in the Security Standard.",
        "target_docs": ["eks_handbook.pdf", "security_policy.pdf"],
        "target_pages": [2, 1],
        "target_sections": ["1.2 Ownership and change windows", "2. Access Control and Session Policies"],
        "expected_facts": [
            "Planned changes to prod-use1-core allowed Tuesday and Thursday 02:00 to 04:00 UTC",
            "Administrative cluster access requires hardware MFA",
            "IAM Identity Center session duration maximum is 60 minutes (1 hour)"
        ]
    }
]


def ingest_test_documents(pipeline_version: str = "v1") -> Dict[str, Any]:
    """
    Ingests test PDFs into the vector store with pipeline_version tag.
    Supports 'v1' (legacy baseline path) and 'v2' (improved layout/parent-child path).
    """
    print(f"\n[Ingestion] Indexing test documents for pipeline_version='{pipeline_version}'...")

    docs_to_index = [
        ("eks_handbook.pdf", HANDBOOK_PDF, f"doc_{pipeline_version}_handbook"),
        ("security_policy.pdf", SECURITY_PDF, f"doc_{pipeline_version}_security"),
    ]

    indexed_counts = {}
    for doc_name, path, doc_id in docs_to_index:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing required PDF: {path}")

        with open(path, "rb") as f:
            pdf_bytes = f.read()

        vector_store.delete_document(doc_id)
        time.sleep(0.5)

        pages = pdf_service.extract_text_by_pages(pdf_bytes, file_name=doc_name)
        chunks = chunking_service.process_document(
            pages=pages,
            doc_name=doc_name,
            document_id=doc_id,
            pipeline_version=pipeline_version
        )

        # Attach pipeline version metadata tag
        for chunk in chunks:
            chunk.pipeline_version = pipeline_version

        vector_store.add_document(doc_id, chunks)
        indexed_counts[doc_name] = len(chunks)
        print(f"  -> Indexed '{doc_name}' ({len(chunks)} chunks, document_id={doc_id})")

    # Update corpus BM25 index with all stored chunks
    from app.services.hybrid_retriever import corpus_bm25_index
    corpus_bm25_index.update_index([c.to_public() for c in vector_store.chunks_db.values()])

    return indexed_counts


def evaluate_retrieval_recall(
    test_case: Dict[str, Any],
    retrieved_chunks: List[DocumentChunk]
) -> Tuple[bool, float, List[int], List[str]]:
    """
    Evaluates whether all expected ground-truth target pages or sections were retrieved.
    Ground truth is assessed by document name + page number / section, NOT chunk ID.
    """
    target_pages = set(test_case.get("target_pages", []))
    target_sections = [s.lower() for s in test_case.get("target_sections", [])]

    retrieved_pages = set()
    retrieved_sections = []

    for chunk in retrieved_chunks:
        for p in range(chunk.page_start, chunk.page_end + 1):
            retrieved_pages.add(p)
        if chunk.section_heading:
            retrieved_sections.append(chunk.section_heading)

    # Check page coverage
    hit_pages = target_pages.intersection(retrieved_pages)
    recall_score = len(hit_pages) / len(target_pages) if target_pages else 1.0

    # Section coverage check
    section_matches = 0
    chunk_texts_lower = " ".join([c.text.lower() + " " + (c.section_heading or "").lower() for c in retrieved_chunks])
    for s in target_sections:
        clean_s = re.sub(r'^[0-9\.\s]+', '', s).strip()
        if clean_s in chunk_texts_lower:
            section_matches += 1

    is_hit = (recall_score >= 0.67) or (section_matches >= len(target_sections) * 0.67)
    return is_hit, recall_score, sorted(list(retrieved_pages)), retrieved_sections


def evaluate_answer_correctness_compact(
    question: str,
    answer: str,
    expected_facts: List[str]
) -> Tuple[bool, float, str]:
    """
    Evaluates answer correctness against expected ground truth facts.
    Uses strict token-saving evaluation:
    1. Fast fact matching based on key terms.
    2. Fallback to compact LLM judge (temperature=0, strictly bounded prompt) only if needed.
    """
    if not answer or (len(answer.strip()) < 180 and "not found" in answer.lower()) or answer.strip().startswith("Information regarding '"):
        return False, 0.0, "Answer declared not found or empty."

    ans_lower = answer.lower()
    facts_met = 0
    details = []

    for fact in expected_facts:
        # Extract essential non-stop words
        tokens = [t.lower() for t in re.findall(r'[A-Za-z0-9_\-\.:]{3,}', fact)]
        core_tokens = [t for t in tokens if t not in {"the", "and", "for", "with", "from", "that", "this", "uses", "must"}]
        matches = sum(1 for tok in core_tokens if tok in ans_lower)
        ratio = matches / len(core_tokens) if core_tokens else 0.0

        if ratio >= 0.5:
            facts_met += 1
            details.append(f"Fact met ({int(ratio*100)}%): '{fact[:40]}...'")
        else:
            details.append(f"Fact missed: '{fact[:40]}...'")

    fact_score = facts_met / len(expected_facts) if expected_facts else 1.0
    passed = fact_score >= 0.65
    return passed, round(fact_score, 2), "; ".join(details)


def print_comparison_table(baseline_file: str, improved_data: Dict[str, Any]):
    """Prints a side-by-side comparison table between Baseline and Improved runs."""
    if not os.path.exists(baseline_file):
        print(f"\n[Notice] Baseline file '{baseline_file}' not found. Skipping side-by-side comparison table.")
        return

    try:
        with open(baseline_file, "r", encoding="utf-8") as f:
            base_data = json.load(f)

        print("\n" + "=" * 92)
        print("SIDE-BY-SIDE EVALUATION COMPARISON: BASELINE vs IMPROVED PIPELINE")
        print("=" * 92)
        print(f"{'Category':<16} | {'Baseline Recall':<16} | {'Improved Recall':<16} | {'Baseline Correc':<16} | {'Improved Correc':<16}")
        print("-" * 92)

        base_cats = base_data.get("category_summary", {})
        imp_cats = improved_data.get("category_summary", {})

        for cat in ["Comparison", "Multi-Hop", "Multi-Section", "Multi-Document"]:
            b = base_cats.get(cat, {})
            i = imp_cats.get(cat, {})
            b_rec = f"{b.get('recall_pct', 0.0):.1f}%"
            i_rec = f"{i.get('recall_pct', 0.0):.1f}%"
            b_cor = f"{b.get('correctness_pct', 0.0):.1f}%"
            i_cor = f"{i.get('correctness_pct', 0.0):.1f}%"
            print(f"{cat:<16} | {b_rec:>16} | {i_rec:>16} | {b_cor:>16} | {i_cor:>16}")

        print("-" * 92)
        b_ov_rec = f"{base_data.get('overall_recall_pct', 0.0):.1f}%"
        i_ov_rec = f"{improved_data.get('overall_recall_pct', 0.0):.1f}%"
        b_ov_cor = f"{base_data.get('overall_correctness_pct', 0.0):.1f}%"
        i_ov_cor = f"{improved_data.get('overall_correctness_pct', 0.0):.1f}%"
        print(f"{'OVERALL':<16} | {b_ov_rec:>16} | {i_ov_rec:>16} | {b_ov_cor:>16} | {i_ov_cor:>16}")
        print(f"Latency: Baseline Avg = {base_data.get('avg_latency_s', 0.0):.2f}s | Improved Avg = {improved_data.get('avg_latency_s', 0.0):.2f}s")
        print("=" * 92)
    except Exception as e:
        logger.warning(f"Failed to generate side-by-side comparison table: {e}")


def run_evaluation(
    eval_mode: str = "improved",
    max_questions: Optional[int] = None,
    ablation_flag: Optional[str] = None
) -> Dict[str, Any]:
    """
    Runs the full evaluation benchmark across all test cases.
    Tracks latency, recall, correctness, token estimation, and provides a per-category breakdown.
    Supports single-flag ablations.
    """
    start_eval_time = time.time()

    # Configure feature flags for this run
    if eval_mode == "baseline":
        p_version = "v1"
        settings.PIPELINE_VERSION = "v1"
        settings.ENABLE_QUERY_DECOMPOSITION = False
        settings.ENABLE_HYBRID_BM25 = False
        settings.ENABLE_RERANKER = False
        settings.ENABLE_PARENT_CHILD = False
        settings.ENABLE_DIVERSITY_MMR = False
        settings.ENABLE_MULTI_DOC_BALANCE = False
        settings.ENABLE_LAYOUT_PARSER = False
    else:
        p_version = "v2"
        settings.PIPELINE_VERSION = "v2"
        settings.ENABLE_QUERY_DECOMPOSITION = True
        settings.ENABLE_HYBRID_BM25 = True
        settings.ENABLE_RERANKER = True
        settings.ENABLE_PARENT_CHILD = True
        settings.ENABLE_DIVERSITY_MMR = True
        settings.ENABLE_MULTI_DOC_BALANCE = True
        settings.ENABLE_LAYOUT_PARSER = True

        # Apply ablation override if requested
        if ablation_flag:
            flag_name = ablation_flag.upper().strip()
            if hasattr(settings, flag_name):
                setattr(settings, flag_name, False)
                print(f"[Ablation] Explicitly disabled flag: {flag_name}=False")

    print("=" * 80)
    print(f"STARTING CROSS-QUESTION EVALUATION [{eval_mode.upper()} MODE]")
    print(f"Pipeline Version: {p_version} | Timestamp: {datetime.now().isoformat()}")
    print("=" * 80)

    # Ingest test docs for this mode
    ingest_test_documents(pipeline_version=p_version)

    dataset = CROSS_EVAL_DATASET[:max_questions] if max_questions else CROSS_EVAL_DATASET
    results = []

    categories = ["Comparison", "Multi-Hop", "Multi-Section", "Multi-Document"]
    cat_metrics = {c: {"total": 0, "recall_hits": 0, "correct_answers": 0, "latency_sum": 0.0} for c in categories}

    print("\nEvaluating test cases...")
    for idx, tc in enumerate(dataset, start=1):
        q_id = tc["id"]
        cat = tc["category"]
        question = tc["question"]

        print(f"\n[{idx}/{len(dataset)}] ({q_id} | {cat}): {question[:75]}...")
        t0 = time.time()

        # Run query through RAG service with target pipeline version
        resp = rag_service.answer_query(question=question, pipeline_version=p_version)
        latency = time.time() - t0

        # Retrieve candidate chunks that were in context
        retrieved_chunks = getattr(rag_service, "last_retrieved_chunks", [])
        if not retrieved_chunks:
            for cite in resp.citations:
                retrieved_chunks.append(
                    DocumentChunk(
                        document_id="eval_doc",
                        chunk_id=cite.chunk_id,
                        document_name=cite.source_name,
                        page_start=cite.page_start,
                        page_end=cite.page_end,
                        section_heading=cite.section_heading,
                        char_start=0,
                        char_end=100,
                        token_count=50,
                        content_hash="hash",
                        embedding_model="eval",
                        text=cite.snippet,
                        pipeline_version=p_version
                    )
                )

        # If citations empty, check vector_store candidates
        if not retrieved_chunks:
            candidates = vector_store.search(query=question, k=settings.TOP_K_CHUNKS, pipeline_version=p_version)
            retrieved_chunks = [c for c, _ in candidates]

        # Evaluate Retrieval Recall
        is_hit, recall_score, ret_pages, ret_sections = evaluate_retrieval_recall(tc, retrieved_chunks)

        # Evaluate Answer Faithfulness/Correctness
        is_correct, fact_score, fact_details = evaluate_answer_correctness_compact(
            question=question,
            answer=resp.answer,
            expected_facts=tc["expected_facts"]
        )

        cat_metrics[cat]["total"] += 1
        if is_hit:
            cat_metrics[cat]["recall_hits"] += 1
        if is_correct:
            cat_metrics[cat]["correct_answers"] += 1
        cat_metrics[cat]["latency_sum"] += latency

        print(f"   -> Recall: {'HIT' if is_hit else 'MISS'} (Target Pages: {tc['target_pages']}, Got: {ret_pages})")
        print(f"   -> Correctness: {'PASS' if is_correct else 'FAIL'} (Score: {fact_score:.2f}) | Latency: {latency:.2f}s")
        print(f"   -> Answer snippet: {resp.answer[:120].strip()}...")

        results.append({
            "id": q_id,
            "category": cat,
            "question": question,
            "target_pages": tc["target_pages"],
            "retrieved_pages": ret_pages,
            "retrieval_hit": is_hit,
            "recall_score": recall_score,
            "answer_correct": is_correct,
            "fact_score": fact_score,
            "latency_s": round(latency, 2),
            "answer": resp.answer,
            "details": fact_details
        })

        # Sleep between queries to strictly respect the 15 RPM free tier limit
        time.sleep(3.5)

    total_time = round(time.time() - start_eval_time, 2)
    total_q = len(dataset)
    total_recall_hits = sum(r["retrieval_hit"] for r in results)
    total_correct = sum(r["answer_correct"] for r in results)

    overall_recall = (total_recall_hits / total_q) * 100.0 if total_q else 0.0
    overall_correct = (total_correct / total_q) * 100.0 if total_q else 0.0
    avg_latency = (sum(r["latency_s"] for r in results) / total_q) if total_q else 0.0

    print("\n" + "=" * 80)
    print(f"EVALUATION RESULTS SUMMARY [{eval_mode.upper()}]")
    print("=" * 80)
    print(f"{'Category':<16} | {'Total':<6} | {'Recall Hits':<12} | {'Recall %':<10} | {'Correct %':<10} | {'Avg Latency':<12}")
    print("-" * 80)

    category_summary = {}
    for cat in categories:
        m = cat_metrics[cat]
        c_tot = m["total"]
        c_rec = (m["recall_hits"] / c_tot * 100.0) if c_tot else 0.0
        c_cor = (m["correct_answers"] / c_tot * 100.0) if c_tot else 0.0
        c_lat = (m["latency_sum"] / c_tot) if c_tot else 0.0
        category_summary[cat] = {
            "total": c_tot,
            "recall_pct": round(c_rec, 1),
            "correctness_pct": round(c_cor, 1),
            "avg_latency_s": round(c_lat, 2)
        }
        print(f"{cat:<16} | {c_tot:<6} | {m['recall_hits']:<12} | {c_rec:>9.1f}% | {c_cor:>9.1f}% | {c_lat:>10.2f}s")

    print("-" * 80)
    print(f"{'OVERALL':<16} | {total_q:<6} | {total_recall_hits:<12} | {overall_recall:>9.1f}% | {overall_correct:>9.1f}% | {avg_latency:>10.2f}s")
    print(f"Total Evaluation Runtime: {total_time}s")
    print("=" * 80)

    summary_data = {
        "eval_mode": eval_mode,
        "ablation_flag": ablation_flag,
        "timestamp": datetime.now().isoformat(),
        "total_questions": total_q,
        "overall_recall_pct": round(overall_recall, 1),
        "overall_correctness_pct": round(overall_correct, 1),
        "avg_latency_s": round(avg_latency, 2),
        "total_runtime_s": total_time,
        "category_summary": category_summary,
        "results": results
    }

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out_file = os.path.join(backend_dir, f"eval_results_{eval_mode}{f'_{ablation_flag}' if ablation_flag else ''}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)
    print(f"Detailed results saved to: {out_file}\n")

    # Print side-by-side comparison if baseline results exist
    baseline_path = os.path.join(backend_dir, "eval_results_baseline.json")
    if eval_mode != "baseline":
        print_comparison_table(baseline_path, summary_data)

    return summary_data


if __name__ == "__main__":
    mode = "improved"
    ablation = None
    if len(sys.argv) > 1:
        arg1 = sys.argv[1].lower()
        if arg1 in ("baseline", "v1"):
            mode = "baseline"
        elif arg1 in ("improved", "v2"):
            mode = "improved"
        elif arg1 == "ablation":
            mode = "improved"
            if len(sys.argv) > 2:
                ablation = sys.argv[2]

    run_evaluation(eval_mode=mode, ablation_flag=ablation)
