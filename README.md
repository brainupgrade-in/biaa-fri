# biaa-fri — Financial-Report Insight Agent

An agent that reads financial reports (10-K/10-Q PDFs, HTML filings, XBRL) and answers
questions about them **without inventing a number and without giving advice**.

## The problem

Ask a general-purpose LLM "what's this company's current ratio?" over a 200-page annual report
and you hit three failure modes that matter more in finance than almost anywhere else:

1. **Ungrounded figures.** The model emits a number with no way to trace where it came from.
2. **Arithmetic by autocomplete.** LLMs do arithmetic by predicting tokens, so a ratio can come
   out plausibly wrong — the worst kind of wrong in a financial context.
3. **Accidental advice.** "Revenue fell 25%, so you should sell" is regulated speech. An
   analysis tool must not cross that line, even casually.

The app is built around refusing all three:

| Capability | How it is enforced |
|---|---|
| **Source grounding** | Every figure is stored as `(value, unit, source_loc)` with doc, page and section. Figures that can't be located are marked `[UNVERIFIED]` and excluded from computation. |
| **Claim citation** | Responses carry inline anchors (`see Income Statement, p. 12`) and end with a Sources block built from a citation index. |
| **Safe computation** | Ratios are computed by a deterministic module via `RestrictedPython` — **never** by the LLM. It returns `{result, formula, inputs_with_sources}`; the LLM only formats. |
| **Anomaly flagging** | Materiality (% of revenue) and z-score outliers surface with `info`/`warning`/`critical` severity — as observations, never conclusions. |
| **No-advice guardrail** | Advisory language is intercepted on both input and output, offending sentences are rewritten to be observational, and every interception is logged. |
| **Withheld trade tool** | Off unless the user explicitly types `/trade`, and it only produces a draft the user submits themselves. It never places an order. |

Specs: [requirements](todo/001-financial-report-insight-agent-requirements.md) ·
[design](todo/002-financial-report-insight-agent-design.md).

## How LangChain and LangGraph are used

Short version: **LangGraph orchestrates the analysis pipeline; LangChain is used for exactly one
thing.** Both the REST and WebSocket paths run the same compiled graph.

### LangGraph — the analysis pipeline

`backend/agent.py` builds the graph in `build_financial_agent_graph()` and compiles it once at
import as `financial_agent_graph`. `backend/main.py` calls it — `.invoke()` for
`POST /api/analysis/query`, `.astream()` for `WS /ws/analysis/stream` — so one definition drives
both transports.

#### The workflow

This is the compiled graph as it actually runs: every box is a node, every solid arrow an edge.
The dotted line is the conditional-edge router.

```mermaid
flowchart TD
    START([entry]) --> PRE[guardrail_pre_check]
    PRE --> FIG[figure_extraction]
    FIG --> CIT[citation_indexing]
    CIT --> CMP[computation]
    CMP --> ANM[anomaly_detection]
    ANM --> ASM[response_assembly]
    ASM --> POST[guardrail_post_check]

    POST -. should_offer_trade .-> ROUTE{user typed /trade?}
    ROUTE -- offer_trade --> TT[trade_tool]
    ROUTE -- end --> DONE([END])
    TT --> DONE
```

Two nodes from design doc §3.2 are deliberately absent — `document_ingest` and
`analyst_reasoning` — for the reasons in the table below.

#### What is in the graph, and what deliberately isn't

| Design node | Status |
|---|---|
| `guardrail_pre_check` | in the graph |
| `document_ingest` | **not a node** — ingest runs once in `POST /api/documents/upload`; making it a node would re-ingest on every query |
| `figure_extraction` | in the graph |
| `citation_indexing` | in the graph |
| `analyst_reasoning` | **not wired** — it writes `final_response`, which `response_assembly` overwrites two steps later, so it is dead weight by construction |
| `computation` | in the graph |
| `anomaly_detection` | in the graph |
| `response_assembly` | in the graph |
| `guardrail_post_check` | in the graph |
| `trade_tool` | in the graph, reached by a conditional edge |
| `trade_confirmation` | **not a node** — confirmation is a separate request, so it needs a checkpointer to resume; see gaps |

`should_offer_trade` is the conditional-edge router. `handle_trade_confirmation` exists but is
unused, pending the checkpointer.

#### How it is wired

Nodes honour the contract LangGraph expects — take the state, return a **partial** dict to merge:

```python
def guardrail_pre_check(state: FinancialAgentState) -> dict:
    result = pre_check_guardrail(state.user_query)
    if result["detected"]:
        return {"user_query": result["augmented_query"]}
    return {}          # empty dict == no state change
```

`should_offer_trade` returns the string key `add_conditional_edges` dispatches on (`"offer_trade"`
/ `"end"`). The shared state is the Pydantic model `FinancialAgentState` in `shared/schemas.py` —
`StateGraph` derives one channel per field — and each node owns distinct keys, which is why a
merge-based graph fits:

| Node | Writes |
|---|---|
| `guardrail_pre_check` | `user_query` (only when advisory phrasing is detected) |
| `figure_extraction` | `extracted_figures` |
| `citation_indexing` | `citation_index` |
| `computation` | `computations` |
| `anomaly_detection` | `anomalies` |
| `response_assembly` | `final_response` |
| `guardrail_post_check` | `rewritten_response`, `guardrail_interceptions`, `final_response` |
| `trade_tool` | `trade_draft` |

Both transports run the same compiled graph. REST invokes it:

```python
result = FinancialAgentState(**financial_agent_graph.invoke(state))
```

The WebSocket streams it, using `"updates"` to name the node that just ran and `"values"` to carry
the accumulated state, so progress events and the final state come from one traversal:

```python
async for mode, data in financial_agent_graph.astream(
    state, stream_mode=["updates", "values"]
):
    if mode == "updates":
        for node_name in data:
            await websocket.send_json({"type": "token", "content": f"[{node_name}]..."})
    else:
        final = data
```

Because both paths share the graph, `/trade` now behaves identically over REST and WebSocket. It
previously worked only over REST, since each path hand-rolled its own sequence and only one of
them checked `should_offer_trade`.

#### What the graph does not do yet

- **No checkpointing / resumable threads.** `AnalysisRequest` accepts a `thread_id`, but no
  checkpointer is configured, so nothing is persisted between requests and each one replays from
  scratch.
- **No human-in-the-loop trade confirmation.** `POST /api/trade/confirm/{id}` still returns a
  canned response instead of resuming the graph at a `trade_confirmation` node. That needs the
  checkpointer above, since confirmation arrives as a separate request.

### LangChain — one lazy import, for optional LLM extraction

The **only** LangChain use in the codebase is in `backend/agent.py`:

```python
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(
    model=settings.llm_model,                     # default: qwen/qwen3.6-27b
    api_key=settings.groq_api_key,
    base_url="https://api.groq.com/openai/v1",    # Groq's OpenAI-compatible endpoint
)
```

Worth knowing:

- It powers **figure extraction only** (`extract_figures_with_llm`), as an accuracy improvement
  over the regex extractor. Everything else — computation, anomaly detection, guardrails,
  response assembly — is deterministic Python with no LLM in the loop.
- It is **optional**. With no `LLM_API_KEY` set, the function returns `[]` immediately and the
  regex extractor in `extract_figures_from_text` does the work. The app is fully functional with
  no LLM configured at all.
- `ChatOpenAI` here talks to **Groq**, not OpenAI, via an OpenAI-compatible base URL, so
  `LLM_MODEL` must be an id Groq actually serves (e.g. `qwen/qwen3.6-27b`, `qwen/qwen3-32b`,
  `llama-3.3-70b-versatile`). Groq serves no Gemma models.
- `langchain-core` is pinned but never imported directly; it arrives via `langchain-openai` and
  `langgraph`.

Keeping the LLM out of the arithmetic is deliberate: a model that can't do the math can't get
the math wrong (requirement C3).

## Running it

The whole app ships as one image — React UI, API, WebSocket, embedded Chroma and SQLite, one
process on one port:

```bash
docker build -t biaa-fri .
docker run -p 8000:8000 -v biaa-data:/data biaa-fri
```

Then open <http://localhost:8000>.

**Mount the volume.** Without `-v`, SQLite and the Chroma index live in the container's writable
layer and disappear on `docker rm`.

The embedding model (~80MB ONNX `all-MiniLM-L6-v2`) is baked in at build time, so the first
upload is fast and the container needs no network egress at runtime.

### Configuration

| Env var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:////data/app.db` | Point at `postgresql://…` to use Postgres instead. |
| `LLM_API_KEY` | *(empty)* | Enables LLM figure extraction. Unset = regex extractor only. |
| `GROQ_API_KEY` | *(empty)* | Groq credential used by `ChatOpenAI`. |
| `LLM_MODEL` | `llama-3.1-8b-instant` | Groq model id. |
| `CHROMA_EMBEDDED` | `true` | `false` targets an external Chroma at `CHROMA_HOST`/`CHROMA_PORT`. |
| `TRADE_TOOL_ENABLED` | `true` | Master switch for the withheld trade tool. |
| `MATERIALITY_THRESHOLD` | `0.10` | Flag line items above this share of revenue. |
| `Z_SCORE_THRESHOLD` | `2.0` | Outlier threshold for anomaly detection. |

### API

| Endpoint | Purpose |
|---|---|
| `POST /api/documents/upload` | Ingest a PDF/HTML/XBRL/text report. Deduplicates on content hash. |
| `GET /api/documents` | List ingested documents. |
| `POST /api/analysis/query` | Ask a question. Returns response, citations, computations, anomalies. |
| `WS /ws/analysis/stream` | Same pipeline, streamed node by node. |
| `POST /api/trade/draft` | Generate a trade draft (never executes). |
| `GET /api/audit/guardrail-logs` | Guardrail interception log. |
| `GET /health`, `GET /ready` | Health probes. |

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/
uvicorn backend.main:app --reload        # API on :8000
```

`backend/main.py` mounts the built React bundle from `STATIC_DIR` (default `frontend/build`). If
it isn't there, it logs a warning and serves the API only — so `uvicorn` alone is fine for
backend work.

For the frontend:

```bash
cd frontend && npm install && npm run build   # then uvicorn serves it at :8000
```

`npm start` (CRA dev server on :3000) will serve the UI but **its API calls will 404** — the
client calls relative `/api` paths and `frontend/package.json` has no `proxy` field. Either add
`"proxy": "http://localhost:8000"` to it, or use `npm run build` + uvicorn as above.

## Status

Working: document ingest (PDF/HTML/XBRL/text), the LangGraph pipeline behind both REST and
WebSocket, regex + optional LLM figure extraction, citation indexing, deterministic computation,
anomaly detection, both guardrails, the trade-draft tool via a conditional edge, and document
persistence on SQLite or Postgres.

Known gaps:

- **No checkpointing.** `AnalysisRequest.thread_id` is accepted but inert — no checkpointer is
  configured, so nothing resumes across requests.
- **Trade confirmation isn't a graph node.** `POST /api/trade/confirm/{id}` returns a canned
  response; making it a real interrupt/resume step needs the checkpointer above.
  `handle_trade_confirmation` is written but unused until then.
- **Part of the persistence layer is unused.** `backend/database.py` defines repository functions
  for figures, guardrail events and trade drafts that nothing calls yet. Only documents and
  chunks are actually persisted; guardrail logs (`main._audit_log`) and trade drafts still live
  in process memory and are lost on restart.
- **Single worker only.** Because that audit log is per-process, `--workers > 1` would serve
  requests from unshared state. The image pins `--workers 1`.
- **Parts of the test suite fail.** `pytest tests/` currently shows pre-existing failures in the
  API-endpoint and WebSocket suites.
