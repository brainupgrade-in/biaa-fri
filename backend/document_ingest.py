"""Document ingestion: parse PDF/HTML/XBRL documents into structured content."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from io import BytesIO
from typing import Optional

import PyPDF2

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

try:
    from lxml import etree
    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False

from backend.vector_store import vector_store


@dataclass
class DocumentChunk:
    page: int
    section: str
    content: str
    tables: list[dict] = field(default_factory=list)


@dataclass
class IngestedDocument:
    doc_id: str
    filename: str
    doc_type: str
    company: str
    ticker: str
    period: str
    currency: str
    chunks: list[DocumentChunk] = field(default_factory=list)
    content_hash: str = ""


# In-memory store (replaced by DB in production)
_document_store: dict[str, IngestedDocument] = {}


def ingest_document(filename: str, content: bytes) -> IngestedDocument:
    """Ingest a document and store it."""
    doc_id = str(uuid.uuid4())
    content_hash = hashlib.sha256(content).hexdigest()

    doc = IngestedDocument(
        doc_id=doc_id,
        filename=filename,
        doc_type=_detect_doc_type(filename),
        company="",
        ticker="",
        period="",
        currency="USD",
        content_hash=content_hash,
    )

    # Parse content based on document type
    if doc.doc_type == "PDF":
        doc.chunks = _parse_pdf(content, doc_id)
    elif doc.doc_type == "HTML":
        doc.chunks = _parse_html(content, doc_id)
    elif doc.doc_type == "XBRL":
        doc.chunks = _parse_xbrl(content, doc_id)
    else:
        # Fallback to text parsing
        text = content.decode("utf-8", errors="ignore")
        doc.chunks = _parse_text_to_chunks(text, doc_id)

    # Add chunks to vector store
    chunk_dicts = [
        {"page": c.page, "section": c.section, "content": c.content}
        for c in doc.chunks
    ]
    vector_store.add_chunks(doc_id, chunk_dicts)

    _document_store[doc_id] = doc
    return doc


def get_document(doc_id: str) -> IngestedDocument | None:
    """Retrieve a document by ID."""
    return _document_store.get(doc_id)


def list_documents() -> list[IngestedDocument]:
    """List all documents."""
    return list(_document_store.values())


def _detect_doc_type(filename: str) -> str:
    lower = filename.lower()
    if ".pdf" in lower:
        return "PDF"
    if ".html" in lower or ".htm" in lower:
        return "HTML"
    if ".xbrl" in lower:
        return "XBRL"
    return "UNKNOWN"


def _parse_pdf(content: bytes, doc_id: str) -> list[DocumentChunk]:
    """Parse PDF content using PyPDF2."""
    chunks = []
    try:
        pdf_file = BytesIO(content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)

        current_section = "Document"
        current_content = []

        for page_num, page in enumerate(pdf_reader.pages, 1):
            text = page.extract_text()
            if not text:
                continue

            # Simple section detection from headers
            lines = text.split("\n")
            for line in lines:
                stripped = line.strip()
                if stripped and (stripped.isupper() or (len(stripped) < 100 and stripped.endswith(":"))):
                    if current_content:
                        chunks.append(DocumentChunk(
                            page=page_num,
                            section=current_section,
                            content="\n".join(current_content),
                        ))
                        current_content = []
                    current_section = stripped.rstrip(":")
                else:
                    current_content.append(line)

            # Add remaining content for this page
            if current_content:
                chunks.append(DocumentChunk(
                    page=page_num,
                    section=current_section,
                    content="\n".join(current_content),
                ))
                current_content = []

    except Exception as e:
        # Fallback to text parsing if PDF parsing fails
        text = content.decode("utf-8", errors="ignore")
        chunks = _parse_text_to_chunks(text, doc_id)

    return chunks if chunks else [DocumentChunk(page=1, section="General", content="")]


def _parse_html(content: bytes, doc_id: str) -> list[DocumentChunk]:
    """Parse HTML content using BeautifulSoup if available, otherwise regex."""
    text = content.decode("utf-8", errors="ignore")
    
    if BS4_AVAILABLE:
        soup = BeautifulSoup(text, "html.parser")
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        # Get text with structure preserved
        clean_text = soup.get_text(separator="\n", strip=True)
    else:
        # Fallback to regex-based cleaning
        clean_text = re.sub(r"<[^>]+>", "\n", text)
        clean_text = re.sub(r"\s+", " ", clean_text)
    
    return _parse_text_to_chunks(clean_text, doc_id)


def _parse_xbrl(content: bytes, doc_id: str) -> list[DocumentChunk]:
    """Parse XBRL content using lxml if available, otherwise regex."""
    text = content.decode("utf-8", errors="ignore")
    
    if LXML_AVAILABLE:
        try:
            # Parse XBRL as XML
            parser = etree.XMLParser(recover=True, huge_tree=True)
            root = etree.fromstring(text.encode("utf-8"), parser=parser)
            
            # Extract all text content from XBRL elements
            # XBRL uses namespaces, so we extract all text nodes
            texts = root.xpath("//text()")
            clean_text = "\n".join(t.strip() for t in texts if t.strip())
        except etree.XMLSyntaxError:
            # Fallback if XML parsing fails
            clean_text = re.sub(r"<[^>]+>", " ", text)
            clean_text = re.sub(r"\s+", " ", clean_text)
    else:
        # Regex-based extraction for XBRL/XML
        clean_text = re.sub(r"<[^>]+>", " ", text)
        clean_text = re.sub(r"\s+", " ", clean_text)
    
    return _parse_text_to_chunks(clean_text, doc_id)


def _parse_text_to_chunks(text: str, doc_id: str) -> list[DocumentChunk]:
    """Simple text-to-chunks parser."""
    chunks = []
    lines = text.split("\n")
    current_section = "General"
    current_content = []

    for i, line in enumerate(lines):
        if line.strip().startswith("#"):
            if current_content:
                chunks.append(DocumentChunk(
                    page=1,
                    section=current_section,
                    content="\n".join(current_content),
                ))
                current_content = []
            current_section = line.strip("# ").strip()
        else:
            current_content.append(line)

        if len(current_content) > 50:
            chunks.append(DocumentChunk(
                page=max(1, i // 50),
                section=current_section,
                content="\n".join(current_content),
            ))
            current_content = []

    if current_content:
        chunks.append(DocumentChunk(
            page=max(1, len(lines) // 50),
            section=current_section,
            content="\n".join(current_content),
        ))

    return chunks if chunks else [DocumentChunk(page=1, section="General", content=text)]
