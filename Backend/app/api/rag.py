import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import fitz
from starlette.concurrency import run_in_threadpool
from fastapi import APIRouter, UploadFile, File, HTTPException, status, Request, BackgroundTasks

from app.core.config import settings
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["RAG Documents"])

# In-memory document status & metadata registry
document_store: Dict[str, Dict[str, Any]] = {}


def sync_document_store():
    """Syncs in-memory registry with any pre-existing chunks in the vector store."""
    if not vector_store.chunks_db:
        vector_store.sync_chunks_from_storage()

    for chunk in vector_store.chunks_db.values():
        doc_id = chunk.document_id
        if doc_id not in document_store:
            document_store[doc_id] = {
                "id": doc_id,
                "name": chunk.document_name,
                "page_count": chunk.page_end,
                "chunk_count": 0,
                "status": "ready",
                "reason": None,
                "created_at": datetime.now(timezone.utc)
            }
        matching_chunks = [c for c in vector_store.chunks_db.values() if c.document_id == doc_id]
        document_store[doc_id]["chunk_count"] = len(matching_chunks)
        document_store[doc_id]["page_count"] = max((c.page_end for c in matching_chunks), default=1)


def process_pdf_background(document_id: str, file_name: str, pages_or_content: Any):
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

        if not pages:
            document_store[document_id]["status"] = "failed"
            document_store[document_id]["reason"] = "Could not extract readable text from pages."
            return

        chunks = chunking_service.process_document(
            pages=pages,
            doc_name=file_name,
            document_id=document_id
        )

        vector_store.add_document(document_id, chunks)

        document_store[document_id]["status"] = "ready"
        document_store[document_id]["page_count"] = len(pages)
        document_store[document_id]["chunk_count"] = len(chunks)
        document_store[document_id]["reason"] = None
        logger.info(f"Background indexing completed for document {document_id} ({len(chunks)} chunks).")
    except Exception as exc:
        logger.error(f"Background indexing failed for document {document_id}: {exc}")
        # Ensure nothing partial remains in vector store
        try:
            vector_store.delete_document(document_id)
        except Exception as cleanup_err:
            logger.warning(f"Rollback cleanup failed for document {document_id}: {cleanup_err}")
        document_store[document_id]["status"] = "failed"
        document_store[document_id]["reason"] = str(exc)


@router.post("/upload", response_model=PDFUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_pdf(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    Upload a PDF document.
    Validates file extension, size (MAX_UPLOAD_MB), and extracts text ONCE via run_in_threadpool.
    Returns immediately with document_id and status='processing'.
    Vector embedding runs in the background using the pre-extracted pages (no duplicate parsing).
    """
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

    # 4. Generate stable document ID
    document_id = hashlib.sha256(content).hexdigest()

    # 5. Register in document store
    document_store[document_id] = {
        "id": document_id,
        "name": file.filename,
        "page_count": len(pages),
        "chunk_count": 0,
        "status": "processing",
        "reason": None,
        "created_at": datetime.now(timezone.utc)
    }

    # 6. Dispatch background task with pre-extracted pages (reused, no double-parsing)
    background_tasks.add_task(process_pdf_background, document_id, file.filename, pages)

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
def list_documents():
    """Returns list of all registered documents with processing status and chunk counts."""
    sync_document_store()
    return [
        DocumentSummary(
            id=doc["id"],
            name=doc["name"],
            page_count=doc.get("page_count", 0),
            chunk_count=doc.get("chunk_count", 0),
            status=doc.get("status", "ready")
        )
        for doc in document_store.values()
    ]


@router.get("/status")
def get_system_status():
    """Returns summary of current vector index and configuration parameters."""
    chunks = list(vector_store.chunks_db.values())
    unique_docs = list({c.document_name for c in chunks})
    return {
        "indexed_documents_count": len(unique_docs),
        "documents": unique_docs,
        "total_chunks_indexed": len(chunks),
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
def get_document_status(document_id: str):
    """Returns processing status (processing, ready, or failed) for a document_id."""
    sync_document_store()
    if document_id not in document_store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found."
        )
    doc = document_store[document_id]
    return DocumentStatusResponse(
        document_id=doc["id"],
        status=doc.get("status", "ready"),
        reason=doc.get("reason"),
        page_count=doc.get("page_count", 0),
        chunk_count=doc.get("chunk_count", 0)
    )


@router.post("/{document_id}/reindex")
def reindex_document(document_id: str, pipeline_version: str = "v2"):
    """
    Re-indexes an existing document with the specified pipeline_version ('v1' or 'v2').
    """
    sync_document_store()
    if document_id not in document_store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found."
        )
    doc = document_store[document_id]
    doc_name = doc.get("name", document_id)
    existing_chunks = [c for c in vector_store.chunks_db.values() if c.document_id == document_id]
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
    vector_store.delete_document(document_id)
    vector_store.add_document(document_id, new_chunks)

    document_store[document_id]["chunk_count"] = len(new_chunks)
    document_store[document_id]["status"] = "ready"

    return {
        "status": "success",
        "message": f"Document '{doc_name}' successfully re-indexed with pipeline_version '{pipeline_version}'.",
        "document_id": document_id,
        "new_chunk_count": len(new_chunks),
        "pipeline_version": pipeline_version
    }


@router.delete("/{document_id}")
def delete_document(document_id: str):
    """Removes a document and all its indexed chunks from the vector store."""
    sync_document_store()
    if document_id not in document_store and document_id not in vector_store.list_documents():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found."
        )

    # Delete from Qdrant vector store
    vector_store.delete_document(document_id)

    # Delete from registry
    doc_info = document_store.pop(document_id, None)
    name = doc_info["name"] if doc_info else document_id

    return {
        "status": "success",
        "message": f"Document '{name}' ({document_id}) removed from vector store.",
        "document_id": document_id
    }


@router.post("/ask", response_model=AskAIResponse)
def ask_question(payload: AskAIRequest):
    """
    Ask a question against indexed enterprise knowledge.
    Supports optional document_id to search a specific document.
    Measures and sets real response_time.
    """
    if not payload.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty."
        )

    # If document_id filter is specified, validate existence
    if payload.document_id:
        sync_document_store()
        if payload.document_id not in document_store and payload.document_id not in vector_store.list_documents():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{payload.document_id}' not found."
            )

    start_time = time.time()
    response = rag_service.answer_query(
        question=payload.question,
        doc_filter=payload.document_filter,
        document_id=payload.document_id
    )

    # Real measured response time set directly by the endpoint
    elapsed = round(time.time() - start_time, 2)
    response.response_time = f"{elapsed}s"
    return response


@router.get("/chunks", response_model=List[DocumentChunk])
def get_indexed_chunks():
    """
    Returns public metadata of all indexed chunks.
    Embeddings are strictly excluded from response models.
    """
    return [chunk.to_public() if hasattr(chunk, "to_public") else chunk for chunk in vector_store.chunks_db.values()]


@router.delete("/clear")
def clear_index():
    """Resets the vector index and document registry."""
    vector_store.clear()
    document_store.clear()
    return {"message": "Vector index cleared successfully."}
