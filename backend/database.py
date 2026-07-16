"""Database models and persistence layer."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CHAR,
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import settings


class GUID(TypeDecorator):
    """UUID column that uses native UUID on PostgreSQL and CHAR(36) elsewhere."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            # Callers pass ids as strings; normalise so stored values and query
            # params share one canonical form.
            value = uuid.UUID(str(value))
        return value if dialect.name == "postgresql" else str(value)

    def process_result_value(self, value, dialect):
        if value is None or isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


class Base(DeclarativeBase):
    pass


class Document(Base):
    """Financial document metadata."""

    __tablename__ = "documents"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    doc_type = Column(String(50), nullable=False)
    company = Column(String(255))
    ticker = Column(String(20))
    period = Column(String(50))
    currency = Column(String(10), default="USD")
    content_hash = Column(String(64), unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_documents_company_period", "company", "period"),
        Index("ix_documents_ticker", "ticker"),
    )


class DocumentChunk(Base):
    """Document text chunks for retrieval."""

    __tablename__ = "document_chunks"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    doc_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page = Column(Integer)
    section = Column(String(255))
    content = Column(Text)
    chunk_index = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_chunks_doc_page", "doc_id", "page"),
    )


class ExtractedFigure(Base):
    """Extracted financial figures with source locations."""

    __tablename__ = "extracted_figures"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    doc_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    value = Column(Float)
    unit = Column(String(50), default="USD")
    confidence = Column(String(20), default="high")
    source_page = Column(Integer)
    source_table = Column(String(255))
    source_row = Column(String(100))
    source_col = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_figures_doc_name", "doc_id", "name"),
    )


class Citation(Base):
    """Citation index linking figures to document sections."""

    __tablename__ = "citations"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    doc_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    section = Column(String(255), nullable=False)
    page = Column(Integer, nullable=False)
    figure_refs = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)


class ComputationResult(Base):
    """Computed financial metrics with traceability."""

    __tablename__ = "computations"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    metric = Column(String(100), nullable=False)
    formula = Column(String(500))
    result = Column(Float)
    unit = Column(String(50))
    inputs = Column(JSON)  # List of input figure references
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Anomaly(Base):
    """Detected anomalies in financial data."""

    __tablename__ = "anomalies"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    doc_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    description = Column(Text, nullable=False)
    severity = Column(String(20), nullable=False)  # info, warning, critical
    metric = Column(String(100))
    change_value = Column(Float)
    source_page = Column(Integer)
    source_table = Column(String(255))
    source_row = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_anomalies_doc_severity", "doc_id", "severity"),
    )


class GuardrailEvent(Base):
    """Append-only audit log for guardrail interceptions."""

    __tablename__ = "guardrail_audit_log"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    original_text = Column(Text, nullable=False)
    rewritten_text = Column(Text, nullable=False)
    trigger_keywords = Column(JSON, default=list)
    session_id = Column(String(255), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Make append-only by not allowing updates/deletes via ORM
    __table_args__ = (
        Index("ix_guardrail_session_time", "session_id", "timestamp"),
    )

    def __setattr__(self, name, value):
        # Prevent updates to existing records
        if name != "id" and hasattr(self, "id") and self.id is not None:
            raise AttributeError("GuardrailEvent is append-only")
        super().__setattr__(name, value)


class TradeDraft(Base):
    """Trade drafts generated by the trade tool."""

    __tablename__ = "trade_drafts"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(20), nullable=False, index=True)
    direction = Column(String(10), nullable=False)  # long, short, neutral
    thesis = Column(Text)
    risk_flags = Column(JSON, default=list)
    suggested_position_size = Column(Float)
    confirmed = Column(Boolean, default=False)
    session_id = Column(String(255), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime)

    __table_args__ = (
        Index("ix_trade_drafts_session_time", "session_id", "created_at"),
    )


# Engine and session factory
_engine = None
_session_factory = None


def get_engine():
    """Get or create database engine."""
    global _engine
    if _engine is None:
        url = settings.database_url
        if url.startswith("sqlite"):
            # SQLite is accessed from FastAPI's sync threadpool, so same-thread
            # checking must be off; pool sizing options don't apply.
            _engine = create_engine(
                url,
                pool_pre_ping=True,
                connect_args={"check_same_thread": False},
            )
        else:
            _engine = create_engine(
                url,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
            )
    return _engine


def get_session_factory():
    """Get or create session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


def init_db():
    """Initialize database tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)


def get_db_session() -> Session:
    """Get a new database session."""
    return get_session_factory()()


# Repository functions
def save_document(doc_data: dict) -> Document:
    """Save a document to the database."""
    session = get_db_session()
    try:
        doc = Document(
            id=doc_data.get("doc_id") or uuid.uuid4(),
            filename=doc_data["filename"],
            doc_type=doc_data["doc_type"],
            company=doc_data.get("company", ""),
            ticker=doc_data.get("ticker", ""),
            period=doc_data.get("period", ""),
            currency=doc_data.get("currency", "USD"),
            content_hash=doc_data["content_hash"],
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)
        return doc
    finally:
        session.close()


def get_document(doc_id: str) -> Optional[Document]:
    """Retrieve a document by ID."""
    session = get_db_session()
    try:
        return session.query(Document).filter(Document.id == doc_id).first()
    finally:
        session.close()


def list_documents() -> list[Document]:
    """List all documents."""
    session = get_db_session()
    try:
        return session.query(Document).order_by(Document.created_at.desc()).all()
    finally:
        session.close()


def save_chunks(doc_id: str, chunks: list[dict]) -> list[DocumentChunk]:
    """Save document chunks."""
    session = get_db_session()
    try:
        db_chunks = []
        for i, chunk in enumerate(chunks):
            db_chunk = DocumentChunk(
                doc_id=doc_id,
                page=chunk.get("page", 1),
                section=chunk.get("section", "General"),
                content=chunk.get("content", ""),
                chunk_index=i,
            )
            session.add(db_chunk)
            db_chunks.append(db_chunk)
        session.commit()
        for c in db_chunks:
            session.refresh(c)
        return db_chunks
    finally:
        session.close()


def save_figures(doc_id: str, figures: list[dict]) -> list[ExtractedFigure]:
    """Save extracted figures."""
    session = get_db_session()
    try:
        db_figures = []
        for fig in figures:
            db_fig = ExtractedFigure(
                doc_id=doc_id,
                name=fig.get("name", ""),
                value=fig.get("value"),
                unit=fig.get("unit", "USD"),
                confidence=fig.get("confidence", "high"),
                source_page=fig.get("source_loc", {}).get("page"),
                source_table=fig.get("source_loc", {}).get("table_or_figure"),
                source_row=fig.get("source_loc", {}).get("row_col_or_line"),
            )
            session.add(db_fig)
            db_figures.append(db_fig)
        session.commit()
        for f in db_figures:
            session.refresh(f)
        return db_figures
    finally:
        session.close()


def get_document_by_hash(content_hash: str) -> Optional[Document]:
    """Retrieve a document by its content hash."""
    session = get_db_session()
    try:
        return session.query(Document).filter(Document.content_hash == content_hash).first()
    finally:
        session.close()


def get_chunks_by_doc(doc_id: str) -> list[DocumentChunk]:
    """Get all chunks for a document, in ingest order."""
    session = get_db_session()
    try:
        return (
            session.query(DocumentChunk)
            .filter(DocumentChunk.doc_id == doc_id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )
    finally:
        session.close()


def get_figures_by_doc(doc_id: str) -> list[ExtractedFigure]:
    """Get all figures for a document."""
    session = get_db_session()
    try:
        return session.query(ExtractedFigure).filter(ExtractedFigure.doc_id == doc_id).all()
    finally:
        session.close()


def save_guardrail_event(event: dict) -> GuardrailEvent:
    """Save a guardrail interception event (append-only)."""
    session = get_db_session()
    try:
        db_event = GuardrailEvent(
            timestamp=datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")),
            original_text=event["original_text"],
            rewritten_text=event["rewritten_text"],
            trigger_keywords=event.get("trigger_keywords", []),
            session_id=event.get("session_id", ""),
        )
        session.add(db_event)
        session.commit()
        session.refresh(db_event)
        return db_event
    finally:
        session.close()


def get_guardrail_logs(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, session_id: Optional[str] = None) -> list[GuardrailEvent]:
    """Query guardrail audit logs."""
    session = get_db_session()
    try:
        query = session.query(GuardrailEvent)
        if start_date:
            query = query.filter(GuardrailEvent.timestamp >= start_date)
        if end_date:
            query = query.filter(GuardrailEvent.timestamp <= end_date)
        if session_id:
            query = query.filter(GuardrailEvent.session_id == session_id)
        return query.order_by(GuardrailEvent.timestamp.desc()).all()
    finally:
        session.close()


def save_trade_draft(draft_data: dict) -> TradeDraft:
    """Save a trade draft."""
    session = get_db_session()
    try:
        draft = TradeDraft(
            ticker=draft_data["ticker"],
            direction=draft_data["direction"],
            thesis=draft_data.get("thesis", ""),
            risk_flags=draft_data.get("risk_flags", []),
            suggested_position_size=draft_data.get("suggested_position_size"),
            session_id=draft_data.get("session_id", ""),
        )
        session.add(draft)
        session.commit()
        session.refresh(draft)
        return draft
    finally:
        session.close()


def confirm_trade_draft(draft_id: str) -> Optional[TradeDraft]:
    """Confirm a trade draft (log only, no execution)."""
    session = get_db_session()
    try:
        draft = session.query(TradeDraft).filter(TradeDraft.id == draft_id).first()
        if draft:
            draft.confirmed = True
            draft.confirmed_at = datetime.utcnow()
            session.commit()
            session.refresh(draft)
        return draft
    finally:
        session.close()


def get_trade_drafts(session_id: Optional[str] = None) -> list[TradeDraft]:
    """Get trade drafts."""
    session = get_db_session()
    try:
        query = session.query(TradeDraft).order_by(TradeDraft.created_at.desc())
        if session_id:
            query = query.filter(TradeDraft.session_id == session_id)
        return query.all()
    finally:
        session.close()