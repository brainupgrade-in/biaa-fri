"""FastAPI application for the Financial-Report Insight Agent."""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.agent import (
    citation_indexing,
    computation,
    anomaly_detection,
    figure_extraction,
    guardrail_post_check,
    guardrail_pre_check,
    response_assembly,
    should_offer_trade,
    trade_tool,
)
from backend.config import settings
from backend.database import init_db
from backend.document_ingest import get_document, ingest_document, list_documents
from shared.schemas import (
    AnalysisRequest,
    AnalysisResponse,
    FinancialAgentState,
    TradeDraft,
    TradeRequest,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=settings.log_level)
    logger.info("Financial Insight Agent starting...")
    # Initialize database tables
    init_db()
    yield
    logger.info("Financial Insight Agent shutting down...")


app = FastAPI(
    title="Financial Insight Agent API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "financial-insight-agent"}


@app.get("/ready")
async def ready():
    return {"status": "ready"}


# ---------------------------------------------------------------------------
# Document Management
# ---------------------------------------------------------------------------

@app.post("/api/documents/upload")
async def upload_document(file: UploadFile):
    content = await file.read()
    doc = ingest_document(file.filename, content)
    return {"doc_id": doc.doc_id, "status": "processed", "filename": doc.filename}


@app.get("/api/documents")
async def get_documents():
    docs = list_documents()
    return [{"doc_id": d.doc_id, "filename": d.filename, "doc_type": d.doc_type} for d in docs]


@app.get("/api/documents/{doc_id}")
async def get_document_detail(doc_id: str):
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "doc_id": doc.doc_id,
        "filename": doc.filename,
        "doc_type": doc.doc_type,
        "chunks": len(doc.chunks),
    }


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

@app.post("/api/analysis/query", response_model=AnalysisResponse)
async def query_analysis(request: AnalysisRequest):
    state = FinancialAgentState(
        user_query=request.query,
        document_ids=request.document_ids,
    )

    # Run pipeline
    state_dict = state.model_dump()

    updates = guardrail_pre_check(state)
    state_dict.update(updates)
    state = FinancialAgentState(**state_dict)

    updates = figure_extraction(state)
    state_dict.update(updates)
    state = FinancialAgentState(**state_dict)

    updates = citation_indexing(state)
    state_dict.update(updates)
    state = FinancialAgentState(**state_dict)

    updates = computation(state)
    state_dict.update(updates)
    state = FinancialAgentState(**state_dict)

    updates = anomaly_detection(state)
    state_dict.update(updates)
    state = FinancialAgentState(**state_dict)

    updates = response_assembly(state)
    state_dict.update(updates)
    state = FinancialAgentState(**state_dict)

    updates = guardrail_post_check(state)
    state_dict.update(updates)
    state = FinancialAgentState(**state_dict)

    # Check for trade request
    trade = None
    if should_offer_trade(state) == "offer_trade":
        trade_updates = trade_tool(state)
        state_dict.update(trade_updates)
        state = FinancialAgentState(**state_dict)
        trade = state.trade_draft

    return AnalysisResponse(
        response=state.final_response,
        citations=state.citation_index,
        anomalies=state.anomalies,
        computations=state.computations,
        trade_draft=trade,
    )


# ---------------------------------------------------------------------------
# WebSocket Streaming
# ---------------------------------------------------------------------------

@app.websocket("/ws/analysis/stream")
async def stream_analysis(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_text()
        request = json.loads(data)

        state = FinancialAgentState(
            user_query=request.get("query", ""),
            document_ids=request.get("document_ids", []),
        )

        # Stream pipeline stages
        stages = [
            ("guardrail_pre_check", guardrail_pre_check),
            ("figure_extraction", figure_extraction),
            ("citation_indexing", citation_indexing),
            ("computation", computation),
            ("anomaly_detection", anomaly_detection),
            ("response_assembly", response_assembly),
            ("guardrail_post_check", guardrail_post_check),
        ]

        state_dict = state.model_dump()
        for stage_name, stage_fn in stages:
            await websocket.send_json({"type": "token", "content": f"[{stage_name}]..."})
            updates = stage_fn(state)
            state_dict.update(updates)
            state = FinancialAgentState(**state_dict)

        # Send final response
        await websocket.send_json({"type": "token", "content": state.final_response})
        await websocket.send_json({
            "type": "citations",
            "metadata": {"citations": [c.model_dump() for c in state.citation_index]},
        })
        await websocket.send_json({
            "type": "anomalies",
            "metadata": {"anomalies": [a.model_dump() for a in state.anomalies]},
        })
        await websocket.send_json({
            "type": "computation",
            "metadata": {"computations": [c.model_dump() for c in state.computations]},
        })
        await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.send_json({"type": "error", "content": str(e)})


# ---------------------------------------------------------------------------
# Trade Tool
# ---------------------------------------------------------------------------

@app.post("/api/trade/draft")
async def create_trade_draft(request: TradeRequest):
    state = FinancialAgentState(user_query=f"/trade {request.ticker} {request.direction}")
    trade_updates = trade_tool(state)
    state = FinancialAgentState(**{**state.model_dump(), **trade_updates})
    return state.trade_draft


@app.post("/api/trade/confirm/{draft_id}")
async def confirm_trade(draft_id: str):
    return {"status": "confirmed", "draft_id": draft_id, "message": "Draft logged. No order placed."}


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

# In-memory audit log (production would use DB)
_audit_log: list[dict] = []


@app.get("/api/audit/guardrail-logs")
async def get_guardrail_logs(start_date: str = "", end_date: str = ""):
    return _audit_log


@app.get("/api/audit/trade-drafts")
async def get_trade_drafts(user_id: str = ""):
    return []


@app.get("/api/admin/system-health")
async def system_health():
    return {"status": "healthy", "components": {"backend": "ok", "database": "ok"}}


# Serve the built React app. Mounted last so it only catches paths the API
# routes above didn't claim; html=True falls back to index.html for client
# -side routes. Absent in local dev when the frontend hasn't been built.
_static_dir = os.getenv("STATIC_DIR", "frontend/build")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="frontend")
else:
    logger.warning("Static dir %s not found; serving API only", _static_dir)
