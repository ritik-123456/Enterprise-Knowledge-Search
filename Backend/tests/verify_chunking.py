import os
import sys
import logging

# Ensure Backend directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.services.chunking_service import chunking_service, get_embedding_text, count_tokens
from app.services.pdf_service import pdf_service
from app.services.vector_store import vector_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verify_chunking")


def run_synthetic_verification():
    print("\n" + "=" * 70)
    print("PART 1: SYNTHETIC MULTI-PAGE VERIFICATION (Edge-Case Coverage)")
    print("=" * 70)

    # 1. Page with repeated headers, standalone page numbers, oversized paragraph, soft-hyphen, and heading
    oversized_block = (
        "Enterprise Kubernetes operations require consistent node provisioning, deterministic network routing, "
        "and strict adherence to security baselines across all development, staging, and production clusters. "
    ) * 35  # ~650 tokens (CHUNK_SIZE_TOKENS is 400)

    p1_text = (
        "CONFIDENTIAL ACME CORP\n"
        "Page 1\n"
        "# Cluster Security Architecture\n"
        "All clusters must be provisioned with informa-\ntion security controls.\n"
        + oversized_block + "\n"
        "The cluster operations team guarantees that each microservice\n"
        "INTERNAL USE ONLY\n"
    )

    # Page 2 continues the cross-page sentence from Page 1:
    p2_text = (
        "CONFIDENTIAL ACME CORP\n"
        "2 of 3\n"
        "is assigned a dedicated service account with least privilege RBAC bindings.\n\n"
        "Section 2: Data Retention and Backups\n"
        "Etcd snapshots must be taken every 6 hours and retained in encrypted storage for 30 days.\n"
        "INTERNAL USE ONLY\n"
    )

    p3_text = (
        "CONFIDENTIAL ACME CORP\n"
        "- 3 -\n"
        "Multi-\nTenant isolation is enforced via network policies and namespace quotas.\n"
        "INTERNAL USE ONLY\n"
    )

    pages = [
        {"page": 1, "text": p1_text},
        {"page": 2, "text": p2_text},
        {"page": 3, "text": p3_text},
    ]

    chunks = chunking_service.process_document(pages, "synthetic_manual.pdf", "doc_synth_001")

    total_chunks = len(chunks)
    token_counts = [ch.token_count for ch in chunks]
    min_tokens = min(token_counts) if token_counts else 0
    max_tokens = max(token_counts) if token_counts else 0
    exceeding_count = sum(1 for ch in chunks if ch.token_count > settings.CHUNK_SIZE_TOKENS)
    cross_page_chunks = [ch for ch in chunks if ch.page_start != ch.page_end]

    print(f"Total Chunks Generated : {total_chunks}")
    print(f"Min Token Count        : {min_tokens}")
    print(f"Max Token Count        : {max_tokens} (CHUNK_SIZE_TOKENS = {settings.CHUNK_SIZE_TOKENS})")
    print(f"Chunks Exceeding Limit : {exceeding_count} (Expected: 0)")
    print(f"Cross-Page Chunks Found: {len(cross_page_chunks)}")

    assert exceeding_count == 0, f"Error: {exceeding_count} chunks exceeded {settings.CHUNK_SIZE_TOKENS} tokens!"
    assert len(cross_page_chunks) > 0, "Error: Expected cross-page chunks across pages 1 and 2!"

    print("\n--- First 3 Synthetic Chunks ---")
    for i, ch in enumerate(chunks[:3]):
        emb_text = get_embedding_text(ch)
        print(f"\n[Chunk {i+1}] ID: {ch.chunk_id}")
        print(f"  Pages   : {ch.page_display} (start={ch.page_start}, end={ch.page_end})")
        print(f"  Heading : {ch.section_heading}")
        print(f"  Tokens  : {ch.token_count}")
        print(f"  Snippet : {ch.text[:120]}...")
        print(f"  Emb Text: {emb_text[:140]}...")

    print("\n[OK] Synthetic verification PASSED successfully!")


def run_real_pdf_verification():
    real_pdf_path = r"C:\Users\ritik\Downloads\eks_handbook.pdf"
    if not os.path.exists(real_pdf_path):
        print(f"\n[SKIP] Real PDF not found at {real_pdf_path}.")
        return

    print("\n" + "=" * 70)
    print(f"PART 2: REAL PDF VERIFICATION ({os.path.basename(real_pdf_path)})")
    print("=" * 70)

    with open(real_pdf_path, "rb") as f:
        pdf_bytes = f.read()

    pages = pdf_service.extract_text_by_pages(pdf_bytes, "eks_handbook.pdf")
    print(f"Extracted Pages from PDF: {len(pages)}")

    chunks = chunking_service.process_document(pages, "eks_handbook.pdf")

    total_chunks = len(chunks)
    token_counts = [ch.token_count for ch in chunks]
    min_tokens = min(token_counts) if token_counts else 0
    max_tokens = max(token_counts) if token_counts else 0
    exceeding_count = sum(1 for ch in chunks if ch.token_count > settings.CHUNK_SIZE_TOKENS)
    cross_page_chunks = [ch for ch in chunks if ch.page_start != ch.page_end]

    print(f"Total Chunks Generated : {total_chunks}")
    print(f"Min Token Count        : {min_tokens}")
    print(f"Max Token Count        : {max_tokens} (CHUNK_SIZE_TOKENS = {settings.CHUNK_SIZE_TOKENS})")
    print(f"Chunks Exceeding Limit : {exceeding_count} (Expected: 0)")
    print(f"Cross-Page Chunks Found: {len(cross_page_chunks)}")

    assert exceeding_count == 0, f"Error: {exceeding_count} chunks exceeded CHUNK_SIZE_TOKENS!"

    print("\n--- First 5 Real Chunks ---")
    for i, ch in enumerate(chunks[:5]):
        emb_text = get_embedding_text(ch)
        print(f"\n[Chunk {i+1}] ID: {ch.chunk_id}")
        print(f"  Pages   : {ch.page_display} (start={ch.page_start}, end={ch.page_end})")
        print(f"  Heading : {ch.section_heading}")
        print(f"  Tokens  : {ch.token_count}")
        print(f"  Snippet : {ch.text[:120].replace(chr(10), ' ')}...")
        print(f"  Emb Text: {emb_text[:140].replace(chr(10), ' ')}...")

    # Index into vector store and test semantic retrieval
    print("\n" + "-" * 70)
    print("DEBUG LOGGING: VECTOR STORE INDEXING & RETRIEVAL")
    print("-" * 70)

    doc_id = chunks[0].document_id
    logger.info(f"Re-indexing {len(chunks)} chunks into VectorStore for document_id={doc_id}...")
    vector_store.add_document(doc_id, chunks)
    logger.info("Indexing completed.")

    test_queries = [
        "cluster upgrade procedure and maintenance window",
        "How are etcd backups scheduled and retained?",
        "What are the node provisioning standards?"
    ]

    for q in test_queries:
        print(f"\n>>> Query: '{q}'")
        results = vector_store.search(q, top_k=3, min_similarity=0.1)
        if not results:
            print("    No results returned above similarity cutoff.")
        for rank, (ret_chunk, score) in enumerate(results, 1):
            print(f"    Rank {rank} [Score: {score:.4f}] - Chunk: {ret_chunk.chunk_id} | {ret_chunk.page_display}")
            print(f"           Section: '{ret_chunk.section_heading}'")
            print(f"           Snippet: {ret_chunk.text[:130].replace(chr(10), ' ')}...")

    print("\n[OK] Real PDF verification & debug retrieval PASSED successfully!")


if __name__ == "__main__":
    run_synthetic_verification()
    run_real_pdf_verification()
