"""Shared schemas for the financial-report insight agent."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SourceLocation(BaseModel):
    doc_id: str
    page: int
    table_or_figure: str
    row_col_or_line: str


class ExtractedFigure(BaseModel):
    value: float | None = None
    unit: str = "USD"
    name: str = ""
    source_loc: SourceLocation
    confidence: Literal["high", "medium", "low", "unverified"] = "high"


class Citation(BaseModel):
    doc_id: str
    section: str
    page: int
    figure_refs: list[str] = Field(default_factory=list)


class ComputationResult(BaseModel):
    result: float | None = None
    formula: str = ""
    inputs_with_sources: list[ExtractedFigure] = Field(default_factory=list)
    unit: str = "ratio"
    metric: str = ""
    error: str | None = None


class Anomaly(BaseModel):
    description: str = ""
    severity: Literal["info", "warning", "critical"] = "info"
    source: SourceLocation | None = None
    metric: str = ""
    change_value: float = 0.0


class GuardrailEvent(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    original_text: str
    rewritten_text: str
    trigger_keywords: list[str] = Field(default_factory=list)


class TradeDraft(BaseModel):
    ticker: str
    direction: Literal["long", "short", "neutral"] = "long"
    thesis: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    suggested_position_size: float | None = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class FinancialAgentState(BaseModel):
    user_query: str = ""
    document_ids: list[str] = Field(default_factory=list)
    extracted_figures: list[ExtractedFigure] = Field(default_factory=list)
    citation_index: list[Citation] = Field(default_factory=list)
    computations: list[ComputationResult] = Field(default_factory=list)
    anomalies: list[Anomaly] = Field(default_factory=list)
    guardrail_interceptions: list[GuardrailEvent] = Field(default_factory=list)
    rewritten_response: str | None = None
    trade_draft: TradeDraft | None = None
    trade_confirmed: bool = False
    final_response: str = ""


class AnalysisRequest(BaseModel):
    query: str
    document_ids: list[str] = Field(default_factory=list)
    thread_id: str | None = None


class AnalysisResponse(BaseModel):
    response: str
    citations: list[Citation] = Field(default_factory=list)
    anomalies: list[Anomaly] = Field(default_factory=list)
    computations: list[ComputationResult] = Field(default_factory=list)
    trade_draft: TradeDraft | None = None


class TradeRequest(BaseModel):
    ticker: str
    direction: Literal["long", "short", "neutral"] = "long"
