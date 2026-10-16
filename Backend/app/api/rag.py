import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import fitz
from starlette.concurrency import run_in_threadpool
from fastapi import APIRouter, UploadFile, File, HTTPException, status, Request, BackgroundTasks, Depends

from app.core.config import settings
from app.core.auth_dependency import get_current_user_id
from app.core.rate_limiter import upload_rate_limiter
from app.schemas.rag import (
    PDFUploadResponse,
    AskAIRequest,
    AskAIResponse,
    DocumentChunk,
    DocumentSummary,
    DocumentStatusResponse
)
from app.services.pdf_service import (
    pdf_service,
    PDFProcessingError,
    PDFExtractionError,
    PDFValidationError,
    PDFOversizedError,
    PDFEncryptedError,
    PDFPageLimitError,
    PDFCorruptError,
)
from app.services.chunking_service import chunking_service
from app.services.vector_store import vector_store
from app.services.rag_service import rag_service
from app.services.hybrid_retriever import corpus_bm25_index

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["RAG Documents"])

# In-memory document status & metadata registry keyed strictly by user_id:
# user_document_store[user_id][document_id] = metadata
user_document_store: Dict[str, Dict[str, Dict[str, Any]]] = {}


def sync_document_store(user_id: Optional[str] = None):
    """
    Syncs in-memory registry from persistent Qdrant payload storage.
    user_document_store and vector_store.user_chunks_db act purely as caches;
    Qdrant payload storage is the source of truth for document ownership and chunks.
    """
    if not user_id:
        return
    # On cache miss (not cached or empty), rebuild from Qdrant storage
    if (
        user_id not in user_document_store
        or not user_document_store[user_id]
        or user_id not in vector_store.user_chunks_db
        or not vector_store.user_chunks_db.get(user_id)
    ):
        vector_store.sync_chunks_from_storage(user_id=user_id)

    user_chunks = vector_store.user_chunks_db.get(user_id, {})
    if user_id not in user_document_store:
        user_document_store[user_id] = {}

    for chunk in user_chunks.values():
        doc_id = chunk.document_id
        if doc_id not in user_document_store[user_id]:
            user_document_store[user_id][doc_id] = {
                "id": doc_id,
                "name": chunk.document_name,
                "page_count": chunk.page_end,
                "chunk_count": 0,
                "status": "ready",
                "reason": None,
                "user_id": user_id,
                "created_at": datetime.now(timezone.utc)
            }
        matching_chunks = [c for c in user_chunks.values() if c.document_id == doc_id]
        user_document_store[user_id][doc_id]["chunk_count"] = len(matching_chunks)
        user_document_store[user_id][doc_id]["page_count"] = max((c.page_end for c in matching_chunks), default=1)


def process_pdf_background(document_id: str, file_name: str, pages_or_content: Any, user_id: str):
    """
    Background worker for chunking and vector indexing using pre-extracted pages.
    Runs off the async event loop in a worker thread.
    Rolls back any partial vector store data if any step fails.
    """
    try:
        if isinstance(pages_or_content, bytes):
            pages = pdf_service.extract_text_by_pages(pages_or_content, file_name)
        else:
            pages = pages_or_content

        user_docs = user_document_store.setdefault(user_id, {})

        if not pages:
            if document_id in user_docs:
                user_docs[document_id]["status"] = "failed"
                user_docs[document_id]["reason"] = "Could not extract readable text from pages."
            return

        chunks = chunking_service.process_document(
            pages=pages,
            doc_name=file_name,
            document_id=document_id
        )

        for chunk in chunks:
            chunk.user_id = user_id

        vector_store.add_document(document_id, chunks, user_id=user_id)
        corpus_bm25_index.update_index(chunks, user_id=user_id)

        if document_id in user_docs:
            user_docs[document_id]["status"] = "ready"
            user_docs[document_id]["page_count"] = len(pages)
            user_docs[document_id]["chunk_count"] = len(chunks)
            user_docs[document_id]["reason"] = None
        logger.info(f"Background indexing completed for user {user_id}, doc {document_id} ({len(chunks)} chunks).")
    except Exception as exc:
        logger.error(f"Background indexing failed for user {user_id}, doc {document_id}: {exc}")
        try:
            vector_store.delete_document(document_id, user_id=user_id)
            corpus_bm25_index.delete_document(document_id, user_id=user_id)
        except Exception as cleanup_err:
            logger.warning(f"Rollback cleanup failed for document {document_id}: {cleanup_err}")

        user_docs = user_document_store.setdefault(user_id, {})
        if document_id in user_docs:
            user_docs[document_id]["status"] = "failed"
            user_docs[document_id]["reason"] = str(exc)


@router.post("/upload", response_model=PDFUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_pdf(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id)
):
    """
    Upload a PDF document.
    Enforces server-verified authentication, per-user rate limit, and per-user content-hash scoping.
    Returns immediately with document_id and status='processing'.
    Vector embedding runs in the background tagged with user_id.
    """
    # 0. Persistent shared rate limit per user across processes/restarts
    if not upload_rate_limiter.check_and_record(user_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Upload rate limit exceeded. Please wait a moment before uploading more documents."
        )

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF documents (.pdf) are supported."
        )

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024

    # 1. Fast Header/Metadata check
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds maximum allowed upload size of {settings.MAX_UPLOAD_MB} MB."
        )

    file_size = getattr(file, "size", None)
    if file_size is not None and file_size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds maximum allowed upload size of {settings.MAX_UPLOAD_MB} MB."
        )

    # 2. Memory-bounded streaming read
    chunks_data = []
    total_read = 0
    chunk_buffer_size = 64 * 1024  # 64 KB

    while True:
        chunk = await file.read(chunk_buffer_size)
        if not chunk:
            break
        total_read += len(chunk)
        if total_read > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File exceeds maximum allowed upload size of {settings.MAX_UPLOAD_MB} MB."
            )
        chunks_data.append(chunk)

    content = b"".join(chunks_data)

    # 3. Synchronous text extraction via run_in_threadpool (extract ONCE per upload)
    try:
        pages = await run_in_threadpool(pdf_service.extract_text_by_pages, content, file.filename)
    except PDFValidationError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err)
        )
    except PDFPageLimitError as lim_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(lim_err)
        )
    except PDFEncryptedError as enc_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(enc_err)
        )
    except PDFExtractionError as ext_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(ext_err)
        )
    except PDFProcessingError as proc_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(proc_err)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Failed to process PDF: {str(exc)}"
        )

    # 4. Generate stable document ID strictly scoped by (user_id, content_hash)
    # This guarantees User B's upload never collides or shares state with User A's copy
    content_hash = hashlib.sha256(content).hexdigest()
    document_id = hashlib.sha256(f"{user_id}:{content_hash}".encode()).hexdigest()

    # 5. Register in user's scoped document store
    user_docs = user_document_store.setdefault(user_id, {})
    user_docs[document_id] = {
        "id": document_id,
        "name": file.filename,
        "page_count": len(pages),
        "chunk_count": 0,
        "status": "processing",
        "reason": None,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc)
    }

    # 6. Dispatch background task with pre-extracted pages and user_id
    background_tasks.add_task(process_pdf_background, document_id, file.filename, pages, user_id)

    # Return immediately
    return PDFUploadResponse(
        status="processing",
        document_id=document_id,
        file_name=file.filename,
        total_pages=len(pages),
        total_chunks=0,
        message="Document upload accepted. Embedding started in background."
    )


@router.get("", response_model=List[DocumentSummary])
@router.get("/", response_model=List[DocumentSummary], include_in_schema=False)
def list_documents(user_id: str = Depends(get_current_user_id)):
    """Returns list of all registered documents owned strictly by the authenticated caller."""
    sync_document_store(user_id=user_id)
    user_docs = user_document_store.get(user_id, {})
    return [
        DocumentSummary(
            id=doc["id"],
            name=doc["name"],
            page_count=doc.get("page_count", 0),
            chunk_count=doc.get("chunk_count", 0),
            status=doc.get("status", "ready"),
            user_id=user_id
        )
        for doc in user_docs.values()
    ]


@router.get("/status")
def get_system_status(user_id: str = Depends(get_current_user_id)):
    """Returns summary of vector index and configuration parameters for the caller."""
    sync_document_store(user_id=user_id)
    user_chunks = list(vector_store.user_chunks_db.get(user_id, {}).values())
    unique_docs = list({c.document_name for c in user_chunks})
    return {
        "indexed_documents_count": len(unique_docs),
        "documents": unique_docs,
        "total_chunks_indexed": len(user_chunks),
        "config": {
            "chunk_size_tokens": settings.CHUNK_SIZE_TOKENS,
            "chunk_overlap_tokens": settings.CHUNK_OVERLAP_TOKENS,
            "retrieve_k": settings.RETRIEVE_K,
            "top_k_chunks": settings.TOP_K_CHUNKS,
            "min_similarity": settings.MIN_SIMILARITY,
            "max_upload_mb": settings.MAX_UPLOAD_MB,
            "max_pages": settings.MAX_PAGES,
            "embed_batch_size": settings.EMBED_BATCH_SIZE,
            "llm_max_tokens": settings.LLM_MAX_TOKENS,
            "llm_temperature": settings.LLM_TEMPERATURE
        }
    }


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
def get_document_status(
    document_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Returns processing status for caller's document_id. Returns 404 if not found or unowned."""
    sync_document_store(user_id=user_id)
    user_docs = user_document_store.get(user_id, {})
    if document_id not in user_docs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found."
        )
    doc = user_docs[document_id]
    return DocumentStatusResponse(
        document_id=doc["id"],
        status=doc.get("status", "ready"),
        reason=doc.get("reason"),
        page_count=doc.get("page_count", 0),
        chunk_count=doc.get("chunk_count", 0)
    )


@router.post("/{document_id}/reindex")
def reindex_document(
    document_id: str,
    pipeline_version: str = "v2",
    user_id: str = Depends(get_current_user_id)
):
    """
    Re-indexes an existing document owned by caller with the specified pipeline_version ('v1' or 'v2').
    Returns 404 if document does not exist or is not owned by the caller.
    """
    sync_document_store(user_id=user_id)
    user_docs = user_document_store.get(user_id, {})
    if document_id not in user_docs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found."
        )
    doc = user_docs[document_id]
    doc_name = doc.get("name", document_id)
    existing_chunks = [
        c for c in vector_store.user_chunks_db.get(user_id, {}).values()
        if c.document_id == document_id
    ]
    if not existing_chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No chunk data found to re-index for document '{document_id}'."
        )

    pages_map: Dict[int, List[str]] = {}
    for c in existing_chunks:
        pages_map.setdefault(c.page_start, []).append(c.text)
    pages = [{"page": p, "text": "\n\n".join(txts)} for p, txts in sorted(pages_map.items())]

    new_chunks = chunking_service.process_document(
        pages=pages,
        doc_name=doc_name,
        document_id=document_id,
        pipeline_version=pipeline_version
    )
    for c in new_chunks:
        c.user_id = user_id

    vector_store.delete_document(document_id, user_id=user_id)
    vector_store.add_document(document_id, new_chunks, user_id=user_id)
    corpus_bm25_index.update_index(new_chunks, user_id=user_id)

    user_docs[document_id]["chunk_count"] = len(new_chunks)
    user_docs[document_id]["status"] = "ready"

    return {
        "status": "success",
        "message": f"Document '{doc_name}' successfully re-indexed with pipeline_version '{pipeline_version}'.",
        "document_id": document_id,
        "new_chunk_count": len(new_chunks),
        "pipeline_version": pipeline_version
    }


@router.delete("/clear")
def clear_index(user_id: str = Depends(get_current_user_id)):
    """
    Resets the vector index and document registry strictly for the authenticated caller.
    Never clears other tenants' data.
    """
    vector_store.clear_user_documents(user_id=user_id)
    corpus_bm25_index.clear_user_index(user_id=user_id)
    user_document_store.pop(user_id, None)
    return {"message": "Vector index cleared successfully for user."}


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Removes a document and all its indexed chunks from the vector store.
    Returns 404 (never 403) if document does not exist or is not owned by the caller,
    preventing document ID enumeration attacks.
    """
    sync_document_store(user_id=user_id)
    user_docs = user_document_store.get(user_id, {})
    if document_id not in user_docs and document_id not in vector_store.list_documents(user_id=user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found."
        )

    # Delete from Qdrant vector store and BM25 index
    vector_store.delete_document(document_id, user_id=user_id)
    corpus_bm25_index.delete_document(document_id, user_id=user_id)

    # Delete from local cache
    doc_info = user_docs.pop(document_id, None)
    name = doc_info["name"] if doc_info else document_id

    return {
        "status": "success",
        "message": f"Document '{name}' ({document_id}) removed from vector store.",
        "document_id": document_id
    }


@router.post("/ask", response_model=AskAIResponse)
def ask_question(
    payload: AskAIRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Ask a question against indexed enterprise knowledge strictly for the authenticated caller.
    Citations and chunks are isolated to the caller's tenancy.
    Supports optional document_id to search a specific caller document.
    """
    if not payload.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty."
        )

    # If document_id filter is specified, validate caller owns the document
    if payload.document_id:
        sync_document_store(user_id=user_id)
        user_docs = user_document_store.get(user_id, {})
        if payload.document_id not in user_docs and payload.document_id not in vector_store.list_documents(user_id=user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{payload.document_id}' not found."
            )

    start_time = time.time()
    response = rag_service.answer_query(
        question=payload.question,
        user_id=user_id,
        doc_filter=payload.document_filter,
        document_id=payload.document_id
    )

    elapsed = round(time.time() - start_time, 2)
    response.response_time = f"{elapsed}s"
    return response


@router.get("/chunks", response_model=List[DocumentChunk])
def get_indexed_chunks(user_id: str = Depends(get_current_user_id)):
    """
    Returns public metadata of all indexed chunks for the authenticated caller only.
    Embeddings are strictly excluded from response models.
    """
    user_chunks = vector_store.user_chunks_db.get(user_id, {})
    return [chunk.to_public() if hasattr(chunk, "to_public") else chunk for chunk in user_chunks.values()]
