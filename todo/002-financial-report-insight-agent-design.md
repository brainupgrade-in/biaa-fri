# Financial-Report Insight Agent — Design Document

**Version:** 1.1  
**Status:** Draft  
**Last Updated:** 2026-07-16  
**Tech Stack:** LangChain, LangGraph, FastAPI, React  
**Deployment:** Kind (Kubernetes in Docker)  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [LangGraph Agent Design](#3-langgraph-agent-design)
4. [Component Specifications](#4-component-specifications)
5. [Data Flow & State Management](#5-data-flow--state-management)
6. [API Design](#6-api-design)
7. [Web Application Design](#7-web-application-design)
8. [Implementation Phases](#8-implementation-phases)
9. [Trackable Tasks](#9-trackable-requirements-to-implementation-mapping)
10. [Testing Strategy](#10-testing-strategy)
11. [Deployment Architecture (Kind/Kubernetes)](#11-deployment-architecture-kindkubernetes)

---

## 1. Executive Summary

This document describes the technical design for a financial-report insight agent built with **LangChain** (tools, chains, retrieval) and **LangGraph** (state machine orchestration). The system ingests financial reports, grounds figures to source documents, cites claims, computes safely via a deterministic sandbox, flags anomalies, enforces a no-advice guardrail, and exposes a withheld trade tool. The user interface is a **React web application** communicating with a **FastAPI** backend.

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     React Web Application                       │
│  ┌──────────┐  ┌───────────┐  ┌───────────┐  ┌──────────────┐ │
│  │ Document │  │  Analysis  │  │  Trade    │  │  Admin/      │ │
│  │ Upload   │  │  Chat UI   │  │  Draft UI │  │  Audit Logs  │ │
│  └──────────┘  └───────────┘  └───────────┘  └──────────────┘ │
└───────────────────────────┬─────────────────────────────────────┘
                            │ WebSocket + REST API
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              LangGraph Orchestrator                       │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │   │
│  │  │ Guard   │→ │ Analyst │→ │ Compute │→ │ Anomaly │   │   │
│  │  │ Rail    │  │ Agent   │  │ Module  │  │ Detector│   │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │   │
│  │       ↓            ↓            ↓            ↓          │   │
│  │  ┌─────────────────────────────────────────────────┐   │   │
│  │  │          Post-Check Guardrail + Trade Tool       │   │   │
│  │  └─────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐   │
│  │  Document    │  │  Computation │  │  Audit Log Store    │   │
│  │  Store       │  │  Sandbox     │  │  (append-only)      │   │
│  │  (PostgreSQL)│  │  (Python)    │  │                     │   │
│  └──────────────┘  └──────────────┘  └─────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Technology Choices

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Agent Orchestration | **LangGraph** | State-machine control flow, conditional branching, human-in-the-loop support for trade tool |
| LLM Integration | **LangChain** | Tool abstractions, prompt management, structured output parsers |
| Retrieval / Grounding | **LangChain Retrieval** | Vector store integration for document chunks with metadata |
| Document Parsing | **Unstructured / PyPDF2** | PDF table extraction, XBRL support |
| Backend API | **FastAPI** | Async support, WebSocket for streaming, auto-generated OpenAPI docs |
| Database | **PostgreSQL** | Document store, citation index, audit logs |
| Vector Store | **Chroma / pgvector** | Embedding-based retrieval for document grounding |
| Frontend | **React + TypeScript** | Component-based UI, WebSocket streaming support |
| Computation Sandbox | **RestrictedPython / subprocess** | Deterministic arithmetic with timeout and resource limits |

---

## 3. LangGraph Agent Design

### 3.1 State Schema

```python
from typing import TypedDict, Literal
from langgraph.graph import MessagesState

class FinancialAgentState(TypedDict):
    # Input
    user_query: str
    document_ids: list[str]
    
    # Extracted data
    extracted_figures: list[ExtractedFigure]
    citation_index: list[Citation]
    
    # Computation results
    computations: list[ComputationResult]
    
    # Anomaly detection
    anomalies: list[Anomaly]
    
    # Guardrail
    guardrail_interceptions: list[GuardrailEvent]
    rewritten_response: str | None
    
    # Trade tool
    trade_draft: TradeDraft | None
    trade_confirmed: bool
    
    # Output
    final_response: str

class ExtractedFigure(TypedDict):
    value: float
    unit: str
    source_loc: SourceLocation
    confidence: Literal["high", "medium", "low", "unverified"]

class SourceLocation(TypedDict):
    doc_id: str
    page: int
    table_or_figure: str
    row_col_or_line: str

class Citation(TypedDict):
    doc_id: str
    section: str
    page: int
    figure_refs: list[str]

class ComputationResult(TypedDict):
    result: float
    formula: str
    inputs_with_sources: list[ExtractedFigure]
    unit: str

class Anomaly(TypedDict):
    description: str
    severity: Literal["info", "warning", "critical"]
    source: SourceLocation
    metric: str
    change_value: float

class GuardrailEvent(TypedDict):
    timestamp: str
    original_text: str
    rewritten_text: str
    trigger_keywords: list[str]

class TradeDraft(TypedDict):
    ticker: str
    direction: Literal["long", "short", "neutral"]
    thesis: str
    risk_flags: list[str]
    suggested_position_size: float | None
    timestamp: str
```

### 3.2 Graph Topology

```python
from langgraph.graph import StateGraph, END

def build_financial_agent_graph() -> StateGraph:
    graph = StateGraph(FinancialAgentState)
    
    # Nodes
    graph.add_node("guardrail_pre_check", guardrail_pre_check_node)
    graph.add_node("document_ingest", document_ingest_node)
    graph.add_node("figure_extraction", figure_extraction_node)
    graph.add_node("citation_indexing", citation_indexing_node)
    graph.add_node("analyst_reasoning", analyst_reasoning_node)
    graph.add_node("computation", computation_node)
    graph.add_node("anomaly_detection", anomaly_detection_node)
    graph.add_node("response_assembly", response_assembly_node)
    graph.add_node("guardrail_post_check", guardrail_post_check_node)
    graph.add_node("trade_tool", trade_tool_node)
    graph.add_node("trade_confirmation", trade_confirmation_node)
    
    # Edges
    graph.set_entry_point("guardrail_pre_check")
    graph.add_edge("guardrail_pre_check", "document_ingest")
    graph.add_edge("document_ingest", "figure_extraction")
    graph.add_edge("figure_extraction", "citation_indexing")
    graph.add_edge("citation_indexing", "analyst_reasoning")
    graph.add_edge("analyst_reasoning", "computation")
    graph.add_edge("computation", "anomaly_detection")
    graph.add_edge("anomaly_detection", "response_assembly")
    graph.add_edge("response_assembly", "guardrail_post_check")
    
    # Conditional: trade tool only if user invoked
    graph.add_conditional_edges(
        "guardrail_post_check",
        should_offer_trade_tool,
        {
            "offer_trade": "trade_tool",
            "end": END
        }
    )
    
    graph.add_conditional_edges(
        "trade_tool",
        handle_trade_confirmation,
        {
            "confirm": "trade_confirmation",
            "cancel": END
        }
    )
    
    graph.add_edge("trade_confirmation", END)
    
    return graph.compile()
```

### 3.3 Node Implementations

#### 3.3.1 Guardrail Pre-Check Node

```python
def guardrail_pre_check_node(state: FinancialAgentState) -> dict:
    """Scan user input for advisory-seeking patterns. Never answer advice questions directly."""
    
    advisory_patterns = [
        r"should (I|we) (buy|sell|hold|invest)",
        r"(recommend|suggest) (buying|selling|holding)",
        r"(overweight|underweight|outperform|underperform)",
    ]
    
    for pattern in advisory_patterns:
        if re.search(pattern, state["user_query"], re.IGNORECASE):
            return {
                "user_query": f"[ANALYSIS REQUEST] {state['user_query']}\n"
                             "SYSTEM NOTE: User may be seeking advice. "
                             "Respond with factual analysis only. No recommendations."
            }
    
    return {}
```

#### 3.3.2 Figure Extraction Node

```python
def figure_extraction_node(state: FinancialAgentState) -> dict:
    """Extract all numerical figures from documents with source locations."""
    
    extraction_prompt = ChatPromptTemplate.from_template("""
    Extract ALL numerical figures from the following document sections.
    
    For each figure, provide:
    - value: the numerical value
    - unit: currency or unit (USD, %, shares, etc.)
    - source_loc: { doc_id, page, table_or_figure, row_col_or_line }
    - confidence: high (primary table), medium (footnote), low (narrative), unverified
    
    Document content:
    {document_content}
    
    Return as JSON array of ExtractedFigure objects.
    """)
    
    extracted = []
    for doc_id in state["document_ids"]:
        doc_content = load_document(doc_id)
        result = extraction_prompt | llm | JsonOutputParser()
        figures = result.invoke({"document_content": doc_content})
        extracted.extend(figures)
    
    return {"extracted_figures": extracted}
```

#### 3.3.3 Computation Node

```python
def computation_node(state: FinancialAgentState) -> dict:
    """Delegate arithmetic to deterministic computation module."""
    
    computations = []
    
    for query in identify_computation_queries(state):
        # Validate inputs
        inputs = resolve_figures_for_computation(
            query, 
            state["extracted_figures"]
        )
        
        # Reject unverified inputs
        for inp in inputs:
            if inp["confidence"] == "unverified":
                computations.append({
                    "result": None,
                    "formula": query["formula"],
                    "inputs_with_sources": inputs,
                    "unit": None,
                    "error": "Input has unverified confidence"
                })
                continue
        
        # Execute in sandbox
        result = computation_sandbox.execute(
            formula=query["formula"],
            inputs=inputs
        )
        
        computations.append(result)
    
    return {"computations": computations}
```

#### 3.3.4 Anomaly Detection Node

```python
def anomaly_detection_node(state: FinancialAgentState) -> dict:
    """Detect statistical outliers and materiality violations."""
    
    anomalies = []
    
    # Period-over-period outlier detection
    for metric in state["computations"]:
        if metric.get("formula", "").startswith("delta"):
            z_score = compute_z_score(metric["result"])
            if abs(z_score) > CONFIG.z_score_threshold:
                anomalies.append({
                    "description": f"{metric['metric']} changed by {metric['result']}",
                    "severity": "warning" if abs(z_score) < 3 else "critical",
                    "source": metric["inputs_with_sources"][0]["source_loc"],
                    "metric": metric["metric"],
                    "change_value": metric["result"]
                })
    
    # Materiality checks
    total_revenue = find_figure_by_name(state["extracted_figures"], "Revenue")
    for figure in state["extracted_figures"]:
        if figure["unit"] == total_revenue["unit"]:
            ratio = figure["value"] / total_revenue["value"]
            if ratio > CONFIG.materiality_threshold:
                anomalies.append({
                    "description": f"{figure['name']} is {ratio:.1%} of revenue",
                    "severity": "warning",
                    "source": figure["source_loc"],
                    "metric": figure["name"],
                    "change_value": ratio
                })
    
    return {"anomalies": anomalies}
```

#### 3.3.5 Guardrail Post-Check Node

```python
def guardrail_post_check_node(state: FinancialAgentState) -> dict:
    """Scan final response for advisory language and rewrite if needed."""
    
    advisory_keywords = [
        "you should", "recommend", "buy", "sell", "hold",
        "overweight", "underweight", "outperform", "underperform",
        "suggest", "advise", "opinion"
    ]
    
    response = state["final_response"]
    interceptions = []
    
    sentences = split_into_sentences(response)
    rewritten_sentences = []
    
    for sentence in sentences:
        if any(kw in sentence.lower() for kw in advisory_keywords):
            # Rewrite to observational
            rewritten = rewrite_to_observational(sentence, llm)
            interceptions.append({
                "timestamp": datetime.utcnow().isoformat(),
                "original_text": sentence,
                "rewritten_text": rewritten,
                "trigger_keywords": [kw for kw in advisory_keywords if kw in sentence.lower()]
            })
            rewritten_sentences.append(rewritten)
        else:
            rewritten_sentences.append(sentence)
    
    return {
        "rewritten_response": " ".join(rewritten_sentences),
        "guardrail_interceptions": state["guardrail_interceptions"] + interceptions
    }
```

#### 3.3.6 Trade Tool Node

```python
def trade_tool_node(state: FinancialAgentState) -> dict:
    """Generate trade draft from analysis. Requires explicit user invocation."""
    
    trade_draft = {
        "ticker": extract_ticker_from_query(state["user_query"]),
        "direction": infer_direction(state["anomalies"], state["computations"]),
        "thesis": synthesize_thesis(
            state["extracted_figures"],
            state["computations"],
            state["anomalies"]
        ),
        "risk_flags": [a["description"] for a in state["anomalies"] if a["severity"] in ["warning", "critical"]],
        "suggested_position_size": compute_position_size(
            state["user_risk_params"],
            state["computations"]
        ),
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return {"trade_draft": trade_draft}
```

---

## 4. Component Specifications

### 4.1 LangChain Tools

```python
from langchain_core.tools import tool

@tool
def extract_financial_figures(document_path: str) -> list[ExtractedFigure]:
    """Extract all numerical figures from a financial document with source locations."""
    # Implementation delegates to figure_extraction_node
    pass

@tool
def compute_financial_metric(
    formula: str, 
    inputs: dict[str, float]
) -> ComputationResult:
    """Compute a financial metric using the deterministic sandbox."""
    # Implementation validates and executes in sandbox
    pass

@tool
def check_anomalies(
    figures: list[ExtractedFigure], 
    computations: list[ComputationResult]
) -> list[Anomaly]:
    """Detect anomalies in financial figures and computations."""
    # Implementation runs statistical and rule-based checks
    pass

@tool
def generate_trade_draft(
    ticker: str,
    direction: str,
    analysis_context: str
) -> TradeDraft:
    """Generate a trade draft for user review. Does NOT execute orders."""
    # Implementation creates draft for user confirmation
    pass

@tool
def get_guardrail_audit_log(
    start_date: str, 
    end_date: str
) -> list[GuardrailEvent]:
    """Retrieve guardrail interception logs for compliance audit."""
    # Implementation queries append-only log store
    pass
```

### 4.2 Prompt Templates

```python
ANALYST_SYSTEM_PROMPT = """
You are a financial analysis agent. Your role is to:
1. Extract and present factual data from financial reports
2. Ground every figure to its source document
3. Cite all claims with document references
4. NEVER recommend actions (buy, sell, hold, etc.)
5. Present observations and anomalies without conclusions

You have access to:
- Extracted figures with source locations
- Computed metrics with formulas and inputs
- Detected anomalies with severity levels

When presenting information:
- Use inline citations: (see § Section, line: Item, p. N)
- Include a Sources section at the end
- Mark unverified figures with [UNVERIFIED]
- State anomalies as observations only
"""

COMPUTATION_SYSTEM_PROMPT = """
You are a deterministic computation module. You must:
1. Execute arithmetic operations precisely
2. Return results with formula, inputs, and sources
3. Never interpret results - only compute
4. Return symbolic errors for division-by-zero or overflow
5. Validate unit consistency before operating

Output format:
{
    "result": float,
    "formula": str,
    "inputs_with_sources": list,
    "unit": str,
    "error": str | null
}
"""
```

---

## 5. Data Flow & State Management

### 5.1 Request Lifecycle

```
User Query + Document IDs
        │
        ▼
┌─────────────────────────────────────────┐
│ 1. Guardrail Pre-Check                  │
│    - Detect advisory-seeking patterns   │
│    - Augment query if needed            │
└─────────────────────┬───────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────┐
│ 2. Document Ingestion                   │
│    - Load PDFs/HTML/XBRL               │
│    - Parse tables, text, metadata       │
│    - Store in document store            │
└─────────────────────┬───────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────┐
│ 3. Figure Extraction                    │
│    - LLM extracts figures with sources  │
│    - Confidence scoring                 │
│    - Build extracted_figures list       │
└─────────────────────┬───────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────┐
│ 4. Citation Indexing                    │
│    - Build citation index               │
│    - Link figures to citations          │
│    - Prepare for self-check             │
└─────────────────────┬───────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────┐
│ 5. Analyst Reasoning                    │
│    - LLM analyzes figures               │
│    - Identifies computations needed     │
│    - Drafts initial response            │
└─────────────────────┬───────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────┐
│ 6. Computation Module                   │
│    - Execute in sandbox                 │
│    - Return results with traceability   │
│    - Reject unverified inputs           │
└─────────────────────┬───────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────┐
│ 7. Anomaly Detection                    │
│    - Statistical outlier detection      │
│    - Materiality checks                 │
│    - GAAP/IFRS heuristics               │
└─────────────────────┬───────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────┐
│ 8. Response Assembly                    │
│    - Format with citations              │
│    - Include computation details        │
│    - List anomalies                     │
│    - Add Sources block                  │
└─────────────────────┬───────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────┐
│ 9. Guardrail Post-Check                 │
│    - Scan for advisory language         │
│    - Rewrite if detected                │
│    - Log interceptions                  │
└─────────────────────┬───────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────┐
│ 10. Trade Tool (Optional)               │
│    - Generate draft if user invoked     │
│    - Present confirmation card          │
│    - Log draft for compliance           │
└─────────────────────────────────────────┘
```

### 5.2 State Persistence

```python
# LangGraph checkpointer for conversation history
from langgraph.checkpoint.postgres import PostgresCheckpointer

checkpointer = PostgresSaver.from_conn_string(
    "postgresql://user:pass@localhost/financial_agent"
)

# Compile graph with checkpointer
app = graph.compile(checkpointer=checkpointer)

# Thread-based state management
config = {"configurable": {"thread_id": "user-session-123"}}
result = app.invoke(initial_state, config)
```

---

## 6. API Design

### 6.1 REST Endpoints

```python
from fastapi import FastAPI, UploadFile, WebSocket
from pydantic import BaseModel

app = FastAPI(title="Financial Insight Agent API")

# Document Management
@app.post("/api/documents/upload")
async def upload_document(file: UploadFile) -> dict:
    """Upload and process a financial document."""
    # Returns: { doc_id, status, metadata }

@app.get("/api/documents/{doc_id}")
async def get_document(doc_id: str) -> dict:
    """Retrieve document metadata and extracted figures."""

# Analysis
@app.post("/api/analysis/query")
async def query_analysis(request: AnalysisRequest) -> AnalysisResponse:
    """Submit a query for financial analysis."""
    # Returns: { response, citations, anomalies, computations }

@app.websocket("/ws/analysis/stream")
async def stream_analysis(websocket: WebSocket):
    """Stream analysis response in real-time."""
    # WebSocket for token-by-token streaming

# Trade Tool
@app.post("/api/trade/draft")
async def create_trade_draft(request: TradeRequest) -> TradeDraft:
    """Generate a trade draft for user review."""
    # Returns: { draft_id, ticker, direction, thesis, risk_flags }

@app.post("/api/trade/confirm/{draft_id}")
async def confirm_trade(draft_id: str) -> dict:
    """User confirms trade draft (logs only, no execution)."""

# Compliance & Audit
@app.get("/api/audit/guardrail-logs")
async def get_guardrail_logs(
    start_date: str, 
    end_date: str
) -> list[GuardrailEvent]:
    """Retrieve guardrail interception logs."""

@app.get("/api/audit/trade-drafts")
async def get_trade_drafts(user_id: str) -> list[TradeDraft]:
    """Retrieve trade draft history for compliance."""

# Admin
@app.get("/api/admin/system-health")
async def system_health() -> dict:
    """System health check including agent status."""
```

### 6.2 WebSocket Protocol

```typescript
// Client -> Server
interface AnalysisStreamRequest {
  type: "analysis_query";
  query: string;
  document_ids: string[];
  thread_id: string;
}

// Server -> Client
interface AnalysisStreamChunk {
  type: "token" | "citations" | "anomalies" | "computation" | "done";
  content: string;
  metadata?: {
    citations?: Citation[];
    anomalies?: Anomaly[];
    computation?: ComputationResult;
  };
}
```

---

## 7. Web Application Design

### 7.1 Component Structure

```
src/
├── components/
│   ├── DocumentUpload/
│   │   ├── DocumentUploader.tsx
│   │   └── DocumentList.tsx
│   ├── Analysis/
│   │   ├── AnalysisChat.tsx
│   │   ├── MessageBubble.tsx
│   │   ├── CitationTooltip.tsx
│   │   ├── AnomalyBadge.tsx
│   │   └── ComputationCard.tsx
│   ├── TradeTool/
│   │   ├── TradeDraftCard.tsx
│   │   ├── TradeConfirmation.tsx
│   │   └── RiskParameters.tsx
│   ├── Admin/
│   │   ├── GuardrailAuditLog.tsx
│   │   ├── TradeDraftHistory.tsx
│   │   └── SystemHealth.tsx
│   └── shared/
│       ├── ConfidenceIndicator.tsx
│       ├── SourceLink.tsx
│       └── LoadingSpinner.tsx
├── hooks/
│   ├── useAnalysisStream.ts
│   ├── useDocuments.ts
│   └── useTradeTool.ts
├── services/
│   ├── api.ts
│   └── websocket.ts
├── types/
│   └── financial-agent.ts
└── App.tsx
```

### 7.2 Key UI Components

```tsx
// AnalysisChat.tsx - Main analysis interface
export function AnalysisChat() {
  const { messages, sendMessage, isStreaming } = useAnalysisStream();
  
  return (
    <div className="chat-container">
      <DocumentUploader />
      
      <div className="messages">
        {messages.map(msg => (
          <MessageBubble 
            key={msg.id}
            content={msg.content}
            citations={msg.citations}
            anomalies={msg.anomalies}
            computations={msg.computations}
          />
        ))}
      </div>
      
      <ChatInput 
        onSend={sendMessage} 
        disabled={isStreaming}
        placeholder="Ask about the financial report..."
      />
    </div>
  );
}

// MessageBubble.tsx - Renders agent response with inline citations
export function MessageBubble({ content, citations, anomalies }) {
  return (
    <div className="message-bubble">
      <MarkdownContent content={content} />
      
      {anomalies.length > 0 && (
        <AnomalyBadge anomalies={anomalies} />
      )}
      
      {citations.length > 0 && (
        <div className="sources-section">
          <h4>Sources</h4>
          {citations.map(cite => (
            <CitationTooltip key={cite.id} citation={cite} />
          ))}
        </div>
      )}
    </div>
  );
}

// TradeDraftCard.tsx - Trade draft with confirmation
export function TradeDraftCard({ draft, onConfirm, onCancel }) {
  return (
    <div className="trade-draft-card">
      <h3>Trade Draft</h3>
      <div className="draft-details">
        <p><strong>Ticker:</strong> {draft.ticker}</p>
        <p><strong>Direction:</strong> {draft.direction}</p>
        <p><strong>Thesis:</strong> {draft.thesis}</p>
        
        <div className="risk-flags">
          <h4>Risk Flags</h4>
          {draft.risk_flags.map((flag, i) => (
            <span key={i} className="risk-flag">{flag}</span>
          ))}
        </div>
        
        {draft.suggested_position_size && (
          <p><strong>Suggested Size:</strong> {draft.suggested_position_size}</p>
        )}
      </div>
      
      <div className="confirmation-actions">
        <button onClick={onConfirm}>Confirm Draft</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
      
      <p className="disclaimer">
        This is a draft only. No order will be placed. 
        Submit manually through your brokerage.
      </p>
    </div>
  );
}
```

### 7.3 WebSocket Hook

```typescript
// useAnalysisStream.ts
export function useAnalysisStream() {
  const [messages, setMessages] = useState<AnalysisMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  
  const sendMessage = useCallback((query: string, documentIds: string[]) => {
    setIsStreaming(true);
    
    wsRef.current = new WebSocket(`${WS_URL}/ws/analysis/stream`);
    
    wsRef.current.onopen = () => {
      wsRef.current?.send(JSON.stringify({
        type: "analysis_query",
        query,
        document_ids: documentIds,
        thread_id: crypto.randomUUID()
      }));
    };
    
    wsRef.current.onmessage = (event) => {
      const chunk = JSON.parse(event.data);
      
      switch (chunk.type) {
        case "token":
          // Append token to current message
          break;
        case "citations":
          // Attach citations to message
          break;
        case "anomalies":
          // Display anomaly badges
          break;
        case "computation":
          // Show computation card
          break;
        case "done":
          setIsStreaming(false);
          break;
      }
    };
    
    return () => wsRef.current?.close();
  }, []);
  
  return { messages, sendMessage, isStreaming };
}
```

---

## 8. Implementation Phases

### Phase 1: Foundation (Weeks 1-3)
**Goal:** Core infrastructure and document ingestion

- [x] Project setup (FastAPI, React, PostgreSQL)
- [x] Document upload and parsing (PDF, HTML, XBRL) - PyPDF2, basic HTML/XBRL parsers implemented
- [x] Basic LangGraph graph with placeholder nodes (implemented as function-based pipeline)
- [x] Vector store setup for document chunks (ChromaDB embedded)
- [x] Basic WebSocket streaming
- [x] Dockerfiles for all services (backend, sandbox)
- [x] Kind cluster configuration
- [x] Basic Kubernetes manifests

### Phase 2: Core Agent (Weeks 4-6)
**Goal:** Figure extraction and citation system

- [x] Figure extraction node with LLM tools (Groq llama-3.1-8b-instant)
- [x] Source location tracking
- [x] Citation index building
- [x] Basic analyst reasoning with prompt templates
- [x] Inline citation rendering
- [x] Secrets management in Kubernetes
- [x] Persistent volume configuration

### Phase 3: Computation & Anomalies (Weeks 7-9)
**Goal:** Safe computation and anomaly detection

- [x] Python sandbox implementation (RestrictedPython)
- [x] Computation node integration
- [x] Unit validation logic
- [x] Statistical outlier detection
- [x] Materiality threshold checks
- [x] Network policies for sandbox isolation
- [x] Computation service deployment

### Phase 4: Guardrails (Weeks 10-11)
**Goal:** No-advice enforcement and audit logging

- [x] Pre-check guardrail node
- [x] Post-check guardrail node
- [x] Advisory language detection
- [x] Sentence rewriting logic
- [x] Append-only audit log store (PostgreSQL)
- [x] Audit log persistence configuration
- [x] RBAC for audit access

### Phase 5: Trade Tool (Weeks 12-13)
**Goal:** Assistive trade draft with confirmation

- [x] Trade draft generation node
- [x] User invocation via `/trade` command
- [ ] Confirmation card UI
- [x] Trade draft logging
- [x] Position sizing logic
- [x] Trade draft persistence (PostgreSQL)
- [x] Compliance logging to persistent storage

### Phase 6: Admin & Polish (Weeks 14-15)
**Goal:** Admin interface and production readiness

- [ ] Guardrail audit log viewer
- [ ] Trade draft history
- [x] System health dashboard
- [ ] Performance optimization
- [ ] Load testing
- [ ] Monitoring setup (Prometheus/Grafana)
- [ ] CI/CD pipeline
- [ ] Deployment automation scripts

---

## 9. Trackable Requirements-to-Implementation Mapping

| Req ID | Description | Component | Task | Status |
|--------|-------------|-----------|------|--------|
| F-GND-01 | Figure stored as tuple | `figure_extraction_node` | Implement ExtractedFigure schema | [x] |
| F-GND-02 | Inline anchor | `response_assembly` | Add citation rendering | [x] |
| F-GND-03 | [UNVERIFIED] tag | `figure_extraction_node` | Add confidence scoring | [x] |
| F-GND-04 | Confidence propagation | `computation_node` | Reject low-confidence inputs | [x] |
| F-CIT-01 | Citation blocks | `response_assembly` | Format citation syntax | [x] |
| F-CIT-02 | Sources block | `response_assembly` | Append sources section | [x] |
| F-CIT-03 | Multi-source synthesis | `citation_indexing` | Track source lineage | [x] |
| F-CIT-04 | Hallucination check | `response_assembly` | Self-check against index | [x] |
| F-CMP-01 | Sandbox delegation | `computation_node` | Implement RestrictedPython | [x] |
| F-CMP-02 | Result traceability | `computation_node` | Return formula + inputs | [x] |
| F-CMP-03 | Precision policy | `computation_module` | Format output precision | [x] |
| F-CMP-04 | Div-by-zero guard | `computation_module` | Add symbolic error handling | [x] |
| F-CMP-05 | Unit consistency | `computation_module` | Validate units before op | [x] |
| F-CMP-06 | Temporal consistency | `computation_module` | Validate period alignment | [x] |
| F-ANM-01 | Outlier detection | `anomaly_detection_node` | Implement z-score check | [x] |
| F-ANM-02 | Materiality threshold | `anomaly_detection_node` | Add % of revenue check | [x] |
| F-ANM-03 | GAAP/IFRS heuristics | `anomaly_detection_node` | Add rule-based checks | [x] |
| F-ANM-04 | Severity levels | `anomaly_detection_node` | Map z-score to severity | [x] |
| F-ANM-05 | No conclusions | `analyst_reasoning` | Prompt constraint | [x] |
| F-GRD-01 | Advisory classifier | `guardrail_post_check` | Keyword + LLM check | [x] |
| F-GRD-02 | Sentence rewrite | `guardrail_post_check` | LLM rewrite to observational | [x] |
| F-GRD-03 | Interception logging | `guardrail_post_check` | Append to audit log | [x] |
| F-GRD-04 | System prompt | `analyst_reasoning` | Add hard-constraint | [x] |
| F-TRD-01 | Trade brief schema | `trade_tool_node` | Implement TradeDraft | [x] |
| F-TRD-02 | Disabled by default | `langgraph_edges` | Conditional routing | [x] |
| F-TRD-03 | Confirmation card | `TradeDraftCard.tsx` | UI implementation | [x] |
| F-TRD-04 | No execution | `trade_tool_node` | Log-only confirmation | [x] |
| F-TRD-05 | Draft logging | `trade_tool_node` | Append to trade log | [x] |
| F-TRD-06 | Assistive sizing | `trade_tool_node` | Position size suggestion | [x] |
| UC-01 | Revenue grounding | Full pipeline | E2E test with 10-K | [x] |
| UC-02 | Ratio traceability | Full pipeline | Current ratio E2E test | [x] |
| UC-03 | Margin anomaly | `anomaly_detection_node` | Z-score test case | [x] |
| UC-04 | No-advice enforcement | `guardrail_post_check` | Advisory test case | [x] |
| UC-05 | Trade draft | `trade_tool_node` + UI | `/trade` command E2E | [x] |
| UC-06 | Multi-period validation | `computation_node` | YoY growth E2E test | [x] |
| UC-07 | Citation audit | `response_assembly` | Citation completeness check | [x] |
| UC-08 | Unverified handling | `computation_node` | Reject unverified E2E | [x] |
| UC-09 | Materiality escalation | `anomaly_detection_node` | Critical severity test | [x] |
| UC-10 | Audit log review | Admin UI + API | Audit log E2E test | [x] |
| NFR-01 | Latency < 8s | Profiling | Load test at p95 | [ ] |
| NFR-02 | Grounding accuracy ≥ 95% | Test suite | Accuracy metrics | [ ] |
| NFR-03 | FP rate ≤ 10% | Test suite | Anomaly FP metrics | [ ] |
| NFR-04 | Guardrail recall ≥ 99% | Test suite | Advisory detection metrics | [ ] |
| NFR-05 | Log retention 7yr | `audit_log_store` | Retention policy | [ ] |
| NFR-06 | PDF/HTML/XBRL | `document_ingest` | Parser implementations | [x] |
| NFR-07 | 100+ concurrent | Load test | Concurrent session test | [ ] |
| DEP-01 | Kind cluster setup | Infrastructure | Create kind-config.yaml | [x] |
| DEP-02 | Dockerfiles | Build | Backend, Frontend, Sandbox | [x] |
| DEP-03 | Kubernetes manifests | Deployment | Deployments, Services, Ingress | [x] |
| DEP-04 | Secrets management | Security | Create secrets.yaml | [x] |
| DEP-05 | Network policies | Security | Isolate sandbox, restrict traffic | [x] |
| DEP-06 | Persistent volumes | Storage | PVCs for DB, vector store | [x] |
| DEP-07 | RBAC | Security | Service accounts, roles | [x] |
| DEP-08 | Health checks | Reliability | Liveness/readiness probes | [x] |
| DEP-09 | Monitoring | Observability | Prometheus/Grafana setup | [x] |
| DEP-10 | CI/CD pipeline | Automation | GitHub Actions workflow | [x] |
| DEP-11 | Deployment scripts | Automation | Setup, deploy, teardown | [x] |
| DEP-12 | Docker Compose | Local Dev | docker-compose.dev.yaml | [x] |

---

## 10. Testing Strategy

### 10.1 Unit Tests

```python
# test_computation_module.py
def test_division_by_zero():
    result = computation_sandbox.execute(
        formula="a / b",
        inputs={"a": 100, "b": 0}
    )
    assert result["result"] is None
    assert result["error"] == "Division by zero"

def test_unit_mismatch():
    result = computation_sandbox.execute(
        formula="a + b",
        inputs={"a": {"value": 100, "unit": "USD"}, 
                "b": {"value": 50, "unit": "EUR"}}
    )
    assert result["error"] == "Unit mismatch"

# test_guardrail.py
def test_advisory_detection():
    response = "You should buy ACME stock immediately."
    events = guardrail_check(response)
    assert len(events) == 1
    assert "buy" in events[0]["trigger_keywords"]

def test_advisory_rewrite():
    original = "You should buy ACME stock."
    rewritten = rewrite_to_observational(original)
    assert "should" not in rewritten.lower()
    assert "recommend" not in rewritten.lower()
```

### 10.2 Integration Tests

```python
# test_grounding_e2e.py
async def test_revenue_grounding():
    doc_id = await upload_test_10k()
    result = await agent.invoke({
        "query": "What was the revenue in FY2024?",
        "document_ids": [doc_id]
    })
    
    # Verify figure extraction
    assert any(f["value"] > 0 for f in result["extracted_figures"])
    
    # Verify source location
    assert result["final_response"].contains("p.")  # Page reference
    
    # Verify no advisory language
    assert "should" not in result["final_response"].lower()

# test_trade_draft_e2e.py
async def test_trade_draft_flow():
    doc_id = await upload_test_10k()
    
    # Analyze first
    await agent.invoke({
        "query": "Analyze ACME financials",
        "document_ids": [doc_id]
    })
    
    # Request trade draft
    result = await agent.invoke({
        "query": "/trade ACME long",
        "document_ids": [doc_id]
    })
    
    # Verify draft created
    assert result["trade_draft"] is not None
    assert result["trade_draft"]["ticker"] == "ACME"
    assert result["trade_confirmed"] is False
```

### 10.3 E2E Tests (Playwright)

```typescript
// tests/analysis-flow.spec.ts
test('complete analysis flow with citations', async ({ page }) => {
  // Upload document
  await page.goto('/');
  await page.click('[data-testid="upload-button"]');
  await page.setInputFiles('[data-testid="file-input"]', 'test-10k.pdf');
  
  // Wait for processing
  await page.waitForSelector('[data-testid="doc-ready"]');
  
  // Ask question
  await page.fill('[data-testid="chat-input"]', 'What was the revenue?');
  await page.click('[data-testid="send-button"]');
  
  // Verify response has citation
  await page.waitForSelector('[data-testid="citation-tooltip"]');
  
  // Verify no advisory language
  const response = await page.textContent('[data-testid="message-bubble"]');
  expect(response).not.toContain('you should');
  expect(response).not.toContain('recommend');
});
```

### 10.4 Performance Tests

```python
# test_performance.py
import asyncio
import time

async def test_latency_p95():
    """Verify p95 latency is under 8 seconds."""
    latencies = []
    
    for _ in range(100):
        start = time.time()
        await agent.invoke({
            "query": "Analyze revenue trends",
            "document_ids": ["test-doc-1"]
        })
        latencies.append(time.time() - start)
    
    p95 = sorted(latencies)[94]
    assert p95 < 8.0, f"p95 latency {p95}s exceeds 8s target"

async def test_concurrent_sessions():
    """Verify 100+ concurrent sessions."""
    async def session(i):
        return await agent.invoke({
            "query": f"Query from session {i}",
            "document_ids": ["test-doc-1"]
        })
    
    results = await asyncio.gather(*[session(i) for i in range(100)])
    assert len(results) == 100
```

---

## 11. Deployment Architecture (Kind/Kubernetes)

### 11.1 Deployment Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Kind Cluster                                │
│                    (financial-agent-kind)                           │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                     Namespace: financial-agent               │   │
│  │                                                              │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │   │
│  │  │ frontend │  │ backend  │  │ postgres │  │ chroma   │   │   │
│  │  │ (React)  │  │ (FastAPI)│  │ (DB)     │  │ (Vector) │   │   │
│  │  │ :3000    │  │ :8000    │  │ :5432    │  │ :8000    │   │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │   │
│  │                                                              │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │                  Services                             │   │   │
│  │  │  frontend-svc → backend-svc → postgres-svc/chroma-svc│   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  │                                                              │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │                  Ingress                              │   │   │
│  │  │  localhost:80 → frontend-svc:3000                     │   │   │
│  │  │  localhost:8000/api → backend-svc:8000                │   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                     Namespace: monitoring                    │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │   │
│  │  │ prometheus│  │ grafana  │  │ loki     │                  │   │
│  │  └──────────┘  └──────────┘  └──────────┘                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 11.2 Kind Cluster Configuration

```yaml
# kind-config.yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: financial-agent-kind
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:
      - containerPort: 80
        hostPort: 80
        protocol: TCP
      - containerPort: 443
        hostPort: 443
        protocol: TCP
      - containerPort: 30080
        hostPort: 30080
        protocol: TCP
      - containerPort: 30090
        hostPort: 30090
        protocol: TCP
  - role: worker
  - role: worker
```

### 11.3 Docker Configuration

#### Backend Dockerfile

```dockerfile
# Dockerfile.backend
FROM python:3.12-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./backend ./backend
COPY ./shared ./shared

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

#### Frontend Dockerfile

```dockerfile
# Dockerfile.frontend
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies
COPY package.json package-lock.json ./
RUN npm ci

# Copy source and build
COPY ./frontend .
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
```

#### Computation Sandbox Dockerfile

```dockerfile
# Dockerfile.sandbox
FROM python:3.12-slim

WORKDIR /sandbox

# Minimal dependencies for computation
RUN pip install --no-cache-dir \
    numpy==1.26.4 \
    pandas==2.2.1

# Restrict capabilities
RUN useradd -m -u 1000 sandbox && \
    chmod 700 /sandbox

USER sandbox

# No network access for security
# (enforced via Kubernetes NetworkPolicy)

CMD ["python", "-m", "sandbox.server"]
```

### 11.4 Kubernetes Manifests

#### Namespace

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: financial-agent
  labels:
    app.kubernetes.io/name: financial-agent
    app.kubernetes.io/version: "1.0.0"
```

#### Backend Deployment

```yaml
# k8s/backend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: financial-agent
  labels:
    app: backend
    component: api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
        component: api
    spec:
      serviceAccountName: backend-sa
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
        - name: backend
          image: financial-agent/backend:latest
          imagePullPolicy: Never  # Use local Kind image
          ports:
            - containerPort: 8000
              name: http
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: backend-secrets
                  key: database-url
            - name: CHROMA_HOST
              value: "chroma-service"
            - name: CHROMA_PORT
              value: "8000"
            - name: LLM_API_KEY
              valueFrom:
                secretKeyRef:
                  name: backend-secrets
                  key: llm-api-key
            - name: ENVIRONMENT
              value: "development"
            - name: LOG_LEVEL
              value: "INFO"
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "2Gi"
              cpu: "1000m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
          volumeMounts:
            - name: documents-pv
              mountPath: /app/documents
            - name: sandbox-tmp
              mountPath: /tmp/sandbox
      volumes:
        - name: documents-pv
          persistentVolumeClaim:
            claimName: documents-pvc
        - name: sandbox-tmp
          emptyDir:
            sizeLimit: 100Mi
```

#### Frontend Deployment

```yaml
# k8s/frontend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: financial-agent
  labels:
    app: frontend
    component: web
spec:
  replicas: 2
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
        component: web
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 101  # nginx user
      containers:
        - name: frontend
          image: financial-agent/frontend:latest
          imagePullPolicy: Never
          ports:
            - containerPort: 3000
              name: http
          resources:
            requests:
              memory: "64Mi"
              cpu: "50m"
            limits:
              memory: "128Mi"
              cpu: "100m"
          livenessProbe:
            httpGet:
              path: /
              port: 3000
            initialDelaySeconds: 10
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /
              port: 3000
            initialDelaySeconds: 5
            periodSeconds: 5
```

#### PostgreSQL Deployment

```yaml
# k8s/postgres-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: financial-agent
  labels:
    app: postgres
    component: database
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
        component: database
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 999
        fsGroup: 999
      containers:
        - name: postgres
          image: postgres:16-alpine
          ports:
            - containerPort: 5432
              name: postgres
          env:
            - name: POSTGRES_DB
              value: "financial_agent"
            - name: POSTGRES_USER
              valueFrom:
                secretKeyRef:
                  name: postgres-secrets
                  key: username
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-secrets
                  key: password
            - name: PGDATA
              value: /var/lib/postgresql/data/pgdata
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "1Gi"
              cpu: "500m"
          livenessProbe:
            exec:
              command:
                - pg_isready
                - -U
                - $(POSTGRES_USER)
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            exec:
              command:
                - pg_isready
                - -U
                - $(POSTGRES_USER)
            initialDelaySeconds: 5
            periodSeconds: 5
          volumeMounts:
            - name: postgres-pv
              mountPath: /var/lib/postgresql/data
      volumes:
        - name: postgres-pv
          persistentVolumeClaim:
            claimName: postgres-pvc
```

#### Chroma Vector Store Deployment

```yaml
# k8s/chroma-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: chroma
  namespace: financial-agent
  labels:
    app: chroma
    component: vector-store
spec:
  replicas: 1
  selector:
    matchLabels:
      app: chroma
  template:
    metadata:
      labels:
        app: chroma
        component: vector-store
    spec:
      containers:
        - name: chroma
          image: chromadb/chroma:latest
          ports:
            - containerPort: 8000
              name: http
          env:
            - name: ANONYMIZED_TELEMETRY
              value: "False"
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
            limits:
              memory: "1Gi"
              cpu: "500m"
          volumeMounts:
            - name: chroma-pv
              mountPath: /chroma/chroma
      volumes:
        - name: chroma-pv
          persistentVolumeClaim:
            claimName: chroma-pvc
```

#### Computation Sandbox Deployment

```yaml
# k8s/sandbox-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sandbox
  namespace: financial-agent
  labels:
    app: sandbox
    component: computation
spec:
  replicas: 2
  selector:
    matchLabels:
      app: sandbox
  template:
    metadata:
      labels:
        app: sandbox
        component: computation
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
      containers:
        - name: sandbox
          image: financial-agent/sandbox:latest
          imagePullPolicy: Never
          ports:
            - containerPort: 8080
              name: http
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 10
```

### 11.5 Services

```yaml
# k8s/services.yaml
apiVersion: v1
kind: Service
metadata:
  name: backend-service
  namespace: financial-agent
spec:
  selector:
    app: backend
  ports:
    - port: 8000
      targetPort: 8000
      name: http
---
apiVersion: v1
kind: Service
metadata:
  name: frontend-service
  namespace: financial-agent
spec:
  selector:
    app: frontend
  ports:
    - port: 3000
      targetPort: 3000
      name: http
---
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
  namespace: financial-agent
spec:
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432
      name: postgres
---
apiVersion: v1
kind: Service
metadata:
  name: chroma-service
  namespace: financial-agent
spec:
  selector:
    app: chroma
  ports:
    - port: 8000
      targetPort: 8000
      name: http
---
apiVersion: v1
kind: Service
metadata:
  name: sandbox-service
  namespace: financial-agent
spec:
  selector:
    app: sandbox
  ports:
    - port: 8080
      targetPort: 8080
      name: http
```

### 11.6 Ingress

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: financial-agent-ingress
  namespace: financial-agent
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
    nginx.ingress.kubernetes.io/websocket-services: backend-service
spec:
  ingressClassName: nginx
  rules:
    - host: localhost
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend-service
                port:
                  number: 3000
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: backend-service
                port:
                  number: 8000
          - path: /ws
            pathType: Prefix
            backend:
              service:
                name: backend-service
                port:
                  number: 8000
```

### 11.7 Persistent Volume Claims

```yaml
# k8s/pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: documents-pvc
  namespace: financial-agent
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 5Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
  namespace: financial-agent
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: chroma-pvc
  namespace: financial-agent
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 5Gi
```

### 11.8 Secrets

```yaml
# k8s/secrets.yaml
apiVersion: v1
kind: Secret
metadata:
  name: backend-secrets
  namespace: financial-agent
type: Opaque
stringData:
  database-url: "postgresql://agent_user:changeme@postgres-service:5432/financial_agent"
  llm-api-key: "your-llm-api-key-here"
---
apiVersion: v1
kind: Secret
metadata:
  name: postgres-secrets
  namespace: financial-agent
type: Opaque
stringData:
  username: "agent_user"
  password: "changeme"
```

### 11.9 Network Policies

```yaml
# k8s/network-policies.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: backend-policy
  namespace: financial-agent
spec:
  podSelector:
    matchLabels:
      app: backend
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: frontend
      ports:
        - port: 8000
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: postgres
        - podSelector:
            matchLabels:
              app: chroma
        - podSelector:
            matchLabels:
              app: sandbox
      ports:
        - port: 5432
        - port: 8000
        - port: 8080
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: sandbox-policy
  namespace: financial-agent
spec:
  podSelector:
    matchLabels:
      app: sandbox
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: backend
      ports:
        - port: 8080
  egress: []  # No outbound traffic allowed
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: postgres-policy
  namespace: financial-agent
spec:
  podSelector:
    matchLabels:
      app: postgres
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: backend
      ports:
        - port: 5432
  egress: []
```

### 11.10 ConfigMaps

```yaml
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  namespace: financial-agent
data:
  ENVIRONMENT: "development"
  LOG_LEVEL: "INFO"
  Z_SCORE_THRESHOLD: "2.0"
  MATERIALITY_THRESHOLD: "0.10"
  PRECISION_DECIMALS: "2"
  COMPUTATION_TIMEOUT: "5"
  MAX_CONCURRENT_SESSIONS: "100"
  AUDIT_LOG_RETENTION_YEARS: "7"
  ADVISORY_KEYWORDS: "you should,recommend,buy,sell,hold,overweight,underweight,outperform,underperform"
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: nginx-config
  namespace: financial-agent
data:
  default.conf: |
    server {
        listen 3000;
        server_name localhost;
        
        location / {
            root /usr/share/nginx/html;
            index index.html;
            try_files $uri $uri/ /index.html;
        }
        
        location /api {
            proxy_pass http://backend-service:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
        
        location /ws {
            proxy_pass http://backend-service:8000;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
        }
    }
```

### 11.11 RBAC

```yaml
# k8s/rbac.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: backend-sa
  namespace: financial-agent
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: backend-role
  namespace: financial-agent
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: backend-rolebinding
  namespace: financial-agent
subjects:
  - kind: ServiceAccount
    name: backend-sa
    namespace: financial-agent
roleRef:
  kind: Role
  name: backend-role
  apiGroup: rbac.authorization.k8s.io
```

### 11.12 Deployment Scripts

#### Setup Script

```bash
#!/bin/bash
# scripts/setup-kind-cluster.sh

set -euo pipefail

CLUSTER_NAME="financial-agent-kind"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Creating Kind cluster..."
kind create cluster --config "$PROJECT_ROOT/kind-config.yaml" --name "$CLUSTER_NAME"

echo "Installing NGINX Ingress Controller..."
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

echo "Waiting for ingress controller..."
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=90s

echo "Building Docker images..."
docker build -t financial-agent/backend:latest -f "$PROJECT_ROOT/Dockerfile.backend" "$PROJECT_ROOT"
docker build -t financial-agent/frontend:latest -f "$PROJECT_ROOT/Dockerfile.frontend" "$PROJECT_ROOT"
docker build -t financial-agent/sandbox:latest -f "$PROJECT_ROOT/Dockerfile.sandbox" "$PROJECT_ROOT"

echo "Loading images into Kind..."
kind load docker-image financial-agent/backend:latest --name "$CLUSTER_NAME"
kind load docker-image financial-agent/frontend:latest --name "$CLUSTER_NAME"
kind load docker-image financial-agent/sandbox:latest --name "$CLUSTER_NAME"

echo "Applying Kubernetes manifests..."
kubectl apply -f "$PROJECT_ROOT/k8s/namespace.yaml"
kubectl apply -f "$PROJECT_ROOT/k8s/secrets.yaml"
kubectl apply -f "$PROJECT_ROOT/k8s/configmap.yaml"
kubectl apply -f "$PROJECT_ROOT/k8s/rbac.yaml"
kubectl apply -f "$PROJECT_ROOT/k8s/pvc.yaml"
kubectl apply -f "$PROJECT_ROOT/k8s/backend-deployment.yaml"
kubectl apply -f "$PROJECT_ROOT/k8s/frontend-deployment.yaml"
kubectl apply -f "$PROJECT_ROOT/k8s/postgres-deployment.yaml"
kubectl apply -f "$PROJECT_ROOT/k8s/chroma-deployment.yaml"
kubectl apply -f "$PROJECT_ROOT/k8s/sandbox-deployment.yaml"
kubectl apply -f "$PROJECT_ROOT/k8s/services.yaml"
kubectl apply -f "$PROJECT_ROOT/k8s/ingress.yaml"
kubectl apply -f "$PROJECT_ROOT/k8s/network-policies.yaml"

echo "Waiting for pods to be ready..."
kubectl wait --namespace financial-agent \
  --for=condition=ready pod \
  --selector=app=backend \
  --timeout=120s

echo "Cluster setup complete!"
echo "Frontend: http://localhost"
echo "Backend API: http://localhost:8000"
echo "PostgreSQL: localhost:5432 (via port-forward)"
```

#### Deployment Script

```bash
#!/bin/bash
# scripts/deploy.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Building new images..."
docker build -t financial-agent/backend:latest -f "$PROJECT_ROOT/Dockerfile.backend" "$PROJECT_ROOT"
docker build -t financial-agent/frontend:latest -f "$PROJECT_ROOT/Dockerfile.frontend" "$PROJECT_ROOT"

echo "Loading images into Kind..."
kind load docker-image financial-agent/backend:latest --name financial-agent-kind
kind load docker-image financial-agent/frontend:latest --name financial-agent-kind

echo "Rolling update deployments..."
kubectl rollout restart deployment/backend -n financial-agent
kubectl rollout restart deployment/frontend -n financial-agent

echo "Waiting for rollout to complete..."
kubectl rollout status deployment/backend -n financial-agent
kubectl rollout status deployment/frontend -n financial-agent

echo "Deployment complete!"
```

#### Teardown Script

```bash
#!/bin/bash
# scripts/teardown.sh

set -euo pipefail

echo "Deleting Kind cluster..."
kind delete cluster --name financial-agent-kind

echo "Cleanup complete!"
```

### 11.13 Health Checks & Monitoring

```yaml
# k8s/monitoring/prometheus-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
  namespace: monitoring
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
    
    scrape_configs:
      - job_name: 'backend'
        kubernetes_sd_configs:
          - role: pod
            namespaces:
              names: ['financial-agent']
        relabel_configs:
          - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
            action: keep
            regex: true
      
      - job_name: 'postgres'
        static_configs:
          - targets: ['postgres-service.financial-agent:5432']
      
      - job_name: 'chroma'
        static_configs:
          - targets: ['chroma-service.financial-agent:8000']
```

```yaml
# k8s/monitoring/grafana-dashboard.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboards
  namespace: monitoring
data:
  financial-agent.json: |
    {
      "dashboard": {
        "title": "Financial Agent Dashboard",
        "panels": [
          {
            "title": "Request Latency (p95)",
            "type": "graph",
            "targets": [{"expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))"}]
          },
          {
            "title": "Guardrail Interceptions",
            "type": "stat",
            "targets": [{"expr": "increase(guardrail_interceptions_total[1h])"}]
          },
          {
            "title": "Active Sessions",
            "type": "gauge",
            "targets": [{"expr": "active_sessions"}]
          },
          {
            "title": "Anomaly Flags",
            "type": "table",
            "targets": [{"expr": "increase(anomaly_flags_total[1h])"}]
          }
        ]
      }
    }
```

### 11.14 CI/CD Pipeline

```yaml
# .github/workflows/deploy.yaml
name: Build and Deploy

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      
      - name: Run tests
        run: pytest tests/ -v --cov=backend --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Build backend
        run: docker build -t financial-agent/backend:latest -f Dockerfile.backend .
      
      - name: Build frontend
        run: docker build -t financial-agent/frontend:latest -f Dockerfile.frontend .
      
      - name: Build sandbox
        run: docker build -t financial-agent/sandbox:latest -f Dockerfile.sandbox .
      
      - name: Load into Kind
        run: |
          kind create cluster --config kind-config.yaml --name financial-agent-kind || true
          kind load docker-image financial-agent/backend:latest --name financial-agent-kind
          kind load docker-image financial-agent/frontend:latest --name financial-agent-kind
          kind load docker-image financial-agent/sandbox:latest --name financial-agent-kind

  deploy:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      
      - name: Deploy to Kind
        run: |
          kubectl apply -f k8s/
          kubectl rollout restart deployment/backend -n financial-agent
          kubectl rollout restart deployment/frontend -n financial-agent
      
      - name: Run smoke tests
        run: |
          kubectl wait --for=condition=ready pod -l app=backend -n financial-agent --timeout=120s
          curl -f http://localhost:8000/health
```

### 11.15 Local Development

```bash
# Makefile for local development

.PHONY: setup dev test deploy teardown

# Create Kind cluster and deploy
setup:
	./scripts/setup-kind-cluster.sh

# Run locally without Kind
dev:
	docker-compose -f docker-compose.dev.yaml up

# Run tests
test:
	pytest tests/ -v
	cd frontend && npm test

# Deploy to Kind
deploy:
	./scripts/deploy.sh

# Teardown cluster
teardown:
	./scripts/teardown.sh

# Port-forward for local access
port-forward:
	kubectl port-forward svc/backend-service 8000:8000 -n financial-agent &
	kubectl port-forward svc/frontend-service 3000:3000 -n financial-agent &
	kubectl port-forward svc/postgres-service 5432:5432 -n financial-agent &

# View logs
logs-backend:
	kubectl logs -f deployment/backend -n financial-agent

logs-frontend:
	kubectl logs -f deployment/frontend -n financial-agent

# Check status
status:
	kubectl get pods -n financial-agent
	kubectl get services -n financial-agent
	kubectl get ingress -n financial-agent
```

#### Docker Compose for Local Development

```yaml
# docker-compose.dev.yaml
version: '3.8'

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://agent_user:changeme@postgres:5432/financial_agent
      - CHROMA_HOST=chroma
      - CHROMA_PORT=8000
      - ENVIRONMENT=development
    depends_on:
      - postgres
      - chroma
      - sandbox
    volumes:
      - ./backend:/app/backend
      - documents:/app/documents

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend

  postgres:
    image: postgres:16-alpine
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_DB=financial_agent
      - POSTGRES_USER=agent_user
      - POSTGRES_PASSWORD=changeme
    volumes:
      - postgres-data:/var/lib/postgresql/data

  chroma:
    image: chromadb/chroma:latest
    ports:
      - "8000:8000"
    volumes:
      - chroma-data:/chroma/chroma

  sandbox:
    build:
      context: .
      dockerfile: Dockerfile.sandbox
    ports:
      - "8080:8080"

volumes:
  postgres-data:
  chroma-data:
  documents:
```

### 11.16 Deployment Checklist

| Task | Command | Status |
|------|---------|--------|
| Create Kind cluster | `kind create cluster --config kind-config.yaml` | [ ] |
| Install NGINX Ingress | `kubectl apply -f ingress-controller.yaml` | [ ] |
| Build backend image | `docker build -t financial-agent/backend:latest -f Dockerfile.backend .` | [ ] |
| Build frontend image | `docker build -t financial-agent/frontend:latest -f Dockerfile.frontend .` | [ ] |
| Build sandbox image | `docker build -t financial-agent/sandbox:latest -f Dockerfile.sandbox .` | [ ] |
| Load images into Kind | `kind load docker-image financial-agent/*:latest` | [ ] |
| Create namespace | `kubectl apply -f k8s/namespace.yaml` | [ ] |
| Create secrets | `kubectl apply -f k8s/secrets.yaml` | [ ] |
| Create configmaps | `kubectl apply -f k8s/configmap.yaml` | [ ] |
| Create PVCs | `kubectl apply -f k8s/pvc.yaml` | [ ] |
| Deploy PostgreSQL | `kubectl apply -f k8s/postgres-deployment.yaml` | [ ] |
| Deploy Chroma | `kubectl apply -f k8s/chroma-deployment.yaml` | [ ] |
| Deploy Backend | `kubectl apply -f k8s/backend-deployment.yaml` | [ ] |
| Deploy Frontend | `kubectl apply -f k8s/frontend-deployment.yaml` | [ ] |
| Deploy Sandbox | `kubectl apply -f k8s/sandbox-deployment.yaml` | [ ] |
| Apply services | `kubectl apply -f k8s/services.yaml` | [ ] |
| Apply ingress | `kubectl apply -f k8s/ingress.yaml` | [ ] |
| Apply network policies | `kubectl apply -f k8s/network-policies.yaml` | [ ] |
| Wait for pods ready | `kubectl wait --for=condition=ready pod -l app=backend` | [ ] |
| Verify health check | `curl http://localhost:8000/health` | [ ] |
| Run smoke tests | `pytest tests/smoke/ -v` | [ ] |

---

## Appendix A: Configuration

```python
# config.py
from pydantic import BaseSettings

class AgentConfig(BaseSettings):
    # Anomaly Detection
    z_score_threshold: float = 2.0
    materiality_threshold: float = 0.10  # 10% of revenue
    
    # Computation
    precision_decimals: int = 2
    computation_timeout_seconds: int = 5
    
    # Guardrail
    advisory_keywords: list[str] = [
        "you should", "recommend", "buy", "sell", "hold",
        "overweight", "underweight", "outperform", "underperform"
    ]
    
    # Trade Tool
    trade_tool_enabled: bool = True  # User must invoke
    
    # Performance
    max_concurrent_sessions: int = 100
    
    # Retention
    audit_log_retention_years: int = 7
    
    # Kubernetes
    kubernetes_namespace: str = "financial-agent"
    kubernetes_cluster: str = "financial-agent-kind"
    
    class Config:
        env_file = ".env"
```

## Appendix C: Kubernetes Environment Variables

```bash
# .env (for local development / Kind secrets)
DATABASE_URL=postgresql://agent_user:changeme@postgres-service:5432/financial_agent
CHROMA_HOST=chroma-service
CHROMA_PORT=8000
LLM_API_KEY=your-llm-api-key-here
ENVIRONMENT=development
LOG_LEVEL=INFO
Z_SCORE_THRESHOLD=2.0
MATERIALITY_THRESHOLD=0.10
PRECISION_DECIMALS=2
COMPUTATION_TIMEOUT=5
MAX_CONCURRENT_SESSIONS=100
AUDIT_LOG_RETENTION_YEARS=7
```

---

## Appendix B: Database Schema

```sql
-- documents table
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR(255) NOT NULL,
    doc_type VARCHAR(50) NOT NULL, -- pdf, html, xbrl
    uploaded_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB,
    content_hash VARCHAR(64) UNIQUE
);

-- extracted_figures table
CREATE TABLE extracted_figures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id UUID REFERENCES documents(id),
    value DECIMAL(20, 4) NOT NULL,
    unit VARCHAR(50) NOT NULL,
    source_page INTEGER,
    source_table VARCHAR(255),
    source_row VARCHAR(100),
    source_col VARCHAR(100),
    confidence VARCHAR(20) NOT NULL,
    extracted_at TIMESTAMP DEFAULT NOW()
);

-- citation_index table
CREATE TABLE citation_index (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id UUID REFERENCES documents(id),
    section VARCHAR(255) NOT NULL,
    page INTEGER NOT NULL,
    figure_refs TEXT[],
    created_at TIMESTAMP DEFAULT NOW()
);

-- guardrail_audit_log (append-only)
CREATE TABLE guardrail_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMP NOT NULL,
    original_text TEXT NOT NULL,
    rewritten_text TEXT NOT NULL,
    trigger_keywords TEXT[],
    session_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

-- trade_drafts table
CREATE TABLE trade_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker VARCHAR(10) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    thesis TEXT NOT NULL,
    risk_flags TEXT[],
    suggested_position_size DECIMAL(20, 4),
    confirmed BOOLEAN DEFAULT FALSE,
    session_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Make guardrail_audit_log append-only
CREATE RULE guardrail_no_update AS ON UPDATE TO guardrail_audit_log DO INSTEAD NOTHING;
CREATE RULE guardrail_no_delete AS ON DELETE TO guardrail_audit_log DO INSTEAD NOTHING;
```
