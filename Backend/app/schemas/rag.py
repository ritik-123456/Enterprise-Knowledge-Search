from datetime import datetime, timezone
from typing import List, Optional, Any
from pydantic import BaseModel, Field, computed_field, model_validator


class PDFPageRecord(BaseModel):
    """
    Per-page extracted record from PDF parser.
    """
    page_index: int = Field(..., description="0-based page index")
    page_label: str = Field(..., description="Printed page label (e.g. 'iv', '12') or index + 1")
    text: str = Field(..., description="Cleaned extracted text with tables and preserved formatting")
    char_count: int = Field(..., description="Total character count in text")
    is_scanned: bool = Field(default=False, description="True if text has fewer than 50 characters")
    tables_found: int = Field(default=0, description="Count of tables found on this page")

    @property
    def page(self) -> int:
        """1-based page number for backward compatibility."""
        return self.page_index + 1

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like access helper for backward compatibility with chunkers."""
        if key == "page":
            return self.page
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        """Subscript access helper for backward compatibility with chunkers."""
        if key == "page":
            return self.page
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)


class PDFHeading(BaseModel):
    """
    Extracted document outline / section heading record.
    """
    title: str = Field(..., description="Section title")
    level: int = Field(..., description="Hierarchy level (1, 2, 3...)")
    page_index: int = Field(..., description="0-based page index where heading appears")



class CitationSource(BaseModel):
    """
    Public citation model referencing specific verified source chunks and page spans.
    Uses @computed_field for 'page' and 'similarity_score' so they are guaranteed
    to appear in all serialized JSON responses for the frontend.
    """
    chunk_id: str = Field(..., description="Unique chunk identifier")
    source_name: str = Field(default="", description="Source document file name or title")
    page_start: int = Field(..., description="First page where the source chunk appears")
    page_end: int = Field(..., description="Last page where the source chunk appears")
    snippet: str = Field(..., description="Relevant text excerpt from the document")
    score: float = Field(..., description="Relevance or cosine similarity score")
    id: Optional[int] = Field(default=None, description="Sequential citation number (e.g. 1, 2)")
    section_heading: Optional[str] = Field(default=None, description="Section heading context if detected")

    @computed_field
    @property
    def page(self) -> int:
        """Computed field for single-page compatibility in UI cards."""
        return self.page_start

    @computed_field
    @property
    def similarity_score(self) -> float:
        """Computed field alias for score."""
        return self.score

    @computed_field
    @property
    def page_display(self) -> str:
        """Formatted page label: 'Page 2' when page_start == page_end, else 'Pages 2-3'."""
        if self.page_start == self.page_end:
            return f"Page {self.page_start}"
        return f"Pages {self.page_start}-{self.page_end}"


class DocumentChunk(BaseModel):
    """
    Public document chunk schema.
    Embeddings are strictly kept OUT of this model and every public response schema.
    Uses @computed_field for 'page_number' so it serializes in JSON.
    """
    document_id: str = Field(..., description="Content hash or ID of the parent document")
    chunk_id: str = Field(..., description="Unique chunk identifier")
    document_name: str = Field(..., description="Name of the source document")
    page_start: int = Field(..., description="Starting page number (1-indexed)")
    page_end: int = Field(..., description="Ending page number (1-indexed)")
    section_heading: Optional[str] = Field(default=None, description="Section heading if detected")
    char_start: int = Field(..., description="Character offset start in the document")
    char_end: int = Field(..., description="Character offset end in the document")
    token_count: Optional[int] = Field(default=0, description="Token count calculated via tiktoken")
    content_hash: str = Field(..., description="SHA-256 hash of the chunk text content")
    embedding_model: str = Field(..., description="Embedding model identifier used for vectorization")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp"
    )
    text: str = Field(..., description="Chunk text content")
    pipeline_version: str = Field(default="v1", description="Pipeline ingestion version: 'v1' (legacy) or 'v2' (improved)")
    parent_text: Optional[str] = Field(default=None, description="Parent section text for small-to-big retrieval")

    @computed_field
    @property
    def page_number(self) -> int:
        """Backward compatibility computed field for single-page consumers."""
        return self.page_start

    @computed_field
    @property
    def page_display(self) -> str:
        """Formatted page label: 'Page 2' when page_start == page_end, else 'Pages 2-3'."""
        if self.page_start == self.page_end:
            return f"Page {self.page_start}"
        return f"Pages {self.page_start}-{self.page_end}"

    def to_public(self) -> "DocumentChunk":
        """Returns self as public DocumentChunk for polymorphism with DocumentChunkInternal."""
        return self


class DocumentChunkInternal(DocumentChunk):
    """
    Separate internal storage model that contains the vector embedding.
    Never returned directly to clients via public API responses.
    """
    embedding: Optional[List[float]] = Field(
        default=None,
        description="Vector embedding floats for semantic search in vector database"
    )

    def to_public(self) -> DocumentChunk:
        """Converts internal storage model to public DocumentChunk without embedding."""
        data = self.model_dump(exclude={"embedding"})
        return DocumentChunk(**data)


class PDFUploadResponse(BaseModel):
    """Response returned upon successful document upload."""
    status: str = "success"
    document_id: str = Field(..., description="Content hash of the uploaded document")
    file_name: str = Field(..., description="Original file name")
    total_pages: int = Field(default=0, description="Total extracted pages")
    total_chunks: int = Field(default=0, description="Total created and indexed chunks")
    message: str = Field(default="", description="Status summary message")


class DocumentSummary(BaseModel):
    """Document summary item returned by GET /api/documents."""
    id: str = Field(..., description="Document content hash identifier")
    name: str = Field(..., description="Document original file name")
    page_count: int = Field(default=0, description="Total pages extracted")
    chunk_count: int = Field(default=0, description="Total chunks indexed")
    status: str = Field(default="ready", description="Processing status: processing, ready, or failed")


class DocumentStatusResponse(BaseModel):
    """Document processing status returned by GET /api/documents/{document_id}/status."""
    document_id: str = Field(..., description="Document content hash identifier")
    status: str = Field(..., description="Status: processing, ready, or failed")
    reason: Optional[str] = Field(default=None, description="Failure reason if status is failed")
    page_count: Optional[int] = Field(default=0, description="Total pages extracted")
    chunk_count: Optional[int] = Field(default=0, description="Total chunks indexed")


class AskAIRequest(BaseModel):
    """Request payload for RAG query."""
    question: str = Field(..., min_length=1, description="User question to answer")
    document_filter: Optional[List[str]] = Field(
        default=None,
        description="Optional list of document names or IDs to restrict search to"
    )
    document_id: Optional[str] = Field(
        default=None,
        description="Optional document ID to restrict search to one document"
    )


class AskAIResponse(BaseModel):
    """
    RAG Query response model.
    Includes explicit 'answerable: bool' indicator so client can distinguish
    grounded enterprise answers from 'not found' or ungrounded queries.

    'response_time' is a REAL measurement taken per request by the endpoint (not a property).
    All presentation fields are real declared fields so they are guaranteed to serialize in JSON.
    """
    question: str = Field(..., description="Original question asked")
    answer: str = Field(..., description="Direct synthesized answer to the query")
    citations: List[CitationSource] = Field(default_factory=list, description="Verified citation sources")
    answerable: bool = Field(..., description="True if answer is found and grounded, False if not found")

    # Real declared fields measured and populated per request by the endpoint:
    response_time: str = Field(..., description="Actual execution measurement in seconds taken per request")
    lead: str = Field(..., description="Concise lead summary sentence")
    key_points: List[str] = Field(default_factory=list, description="Extracted key bullet points")
    confidence: str = Field(default="0%", description="Confidence score percentage string")
    sources_used: int = Field(default=0, description="Count of sources used")
    sources: List[CitationSource] = Field(default_factory=list, description="Alias for citations for UI rendering")

    @model_validator(mode="after")
    def sync_presentation_fields(self):
        if not self.sources and self.citations:
            self.sources = self.citations
        if self.sources_used == 0 and self.citations:
            self.sources_used = len(self.citations)
        return self
