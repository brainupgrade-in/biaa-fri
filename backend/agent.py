"""Financial-Report Insight Agent - Agent nodes and graph."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime

from langgraph.graph import END, StateGraph

from backend.config import settings
from backend.computation import compute_z_score, execute_computation
from backend.guardrail import post_check_guardrail, pre_check_guardrail
from backend.prompts import (
    ANALYST_SYSTEM_PROMPT,
    COMPUTATION_PROMPT,
    REWRITE_TO_OBSERVATIONAL_PROMPT,
    RESPONSE_ASSEMBLY_PROMPT,
    THESIS_SYNTHESIS_PROMPT,
)
from shared.schemas import (
    Anomaly,
    Citation,
    ComputationResult,
    ExtractedFigure,
    FinancialAgentState,
    GuardrailEvent,
    SourceLocation,
    TradeDraft,
)


# ---------------------------------------------------------------------------
# Node: Guardrail Pre-Check
# ---------------------------------------------------------------------------

def guardrail_pre_check(state: FinancialAgentState) -> dict:
    """Scan user input for advisory-seeking patterns."""
    result = pre_check_guardrail(state.user_query)
    if result["detected"]:
        return {"user_query": result["augmented_query"]}
    return {}


# ---------------------------------------------------------------------------
# Node: Figure Extraction (rule-based + LLM)
# ---------------------------------------------------------------------------

FIGURE_EXTRACTION_PROMPT = """Extract ALL numerical figures from the following financial document text.

For each figure, provide:
- name: the exact label/name of the figure (e.g., "Revenue", "Current Assets", "Net Income")
- value: the numerical value
- unit: the unit (USD, %, shares, ratio, etc.)
- confidence: high (primary table), medium (footnote), low (narrative), unverified

Return as JSON array. Only extract actual financial figures, not section headers or dates.

Text:
{text}"""


def extract_figures_with_llm(text: str, doc_id: str, page: int, section: str) -> list[ExtractedFigure]:
    """Extract figures using LLM for better accuracy."""
    if not settings.llm_api_key:
        return []

    try:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )

        # Split text into chunks if too long
        max_chars = 8000
        if len(text) > max_chars:
            text = text[:max_chars]

        prompt = FIGURE_EXTRACTION_PROMPT.format(text=text)
        response = llm.invoke(prompt)
        content = response.content

        # Parse JSON response
        import json
        # Extract JSON from markdown code block if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        figures_data = json.loads(content)

        figures = []
        for fd in figures_data:
            try:
                value = float(fd.get("value", 0)) if fd.get("value") is not None else None
                figures.append(ExtractedFigure(
                    value=value,
                    unit=fd.get("unit", "USD"),
                    name=fd.get("name", ""),
                    source_loc=SourceLocation(
                        doc_id=doc_id,
                        page=page,
                        table_or_figure=section,
                        row_col_or_line=fd.get("name", ""),
                    ),
                    confidence=fd.get("confidence", "high"),
                ))
            except (ValueError, TypeError):
                continue

        return figures
    except Exception:
        # Fall back to regex extraction
        return []


def extract_figures_from_text(text: str, doc_id: str) -> list[ExtractedFigure]:
    """Extract numerical figures from text with source locations."""
    figures = []
    # Pattern: financial label followed by number with optional $ and unit
    # Matches: "Revenue: $5,200,000,000" or "Current Assets: 3,500,000,000"
    # Avoids matching section headers like "INCOME STATEMENT"
    pattern = re.compile(
        r'(?:^|\n)[ \t]*([A-Za-z][A-Za-z ]{2,50}?):[ \t]*\$?([\d,]+(?:\.\d+)?)[ \t]*(million|billion|M|B|%|USD)?',
        re.IGNORECASE | re.MULTILINE,
    )

    page = 1
    # Known section headers to filter out
    section_headers = {
        'income statement', 'balance sheet', 'cash flow statement',
        'notes to financial statements', 'document', 'general',
        'consolidated statements of income', 'consolidated balance sheets',
        'consolidated statements of cash flows', 'consolidated statements of operations',
        'statement of income', 'statement of financial position', 'statement of cash flows',
    }

    for match in pattern.finditer(text):
        label = match.group(1).strip()
        # Filter out section headers (all caps, or known headers)
        if label.isupper() and len(label) < 30:
            continue
        if label.lower() in section_headers:
            continue
        # Filter out labels that are too short or look like headers
        if len(label) < 3:
            continue

        value_str = match.group(2).replace(",", "")
        unit_hint = match.group(3) or "USD"

        try:
            value = float(value_str)
        except ValueError:
            continue

        if unit_hint and unit_hint.lower() in ("million", "m"):
            value *= 1_000_000
        elif unit_hint and unit_hint.lower() in ("billion", "b"):
            value *= 1_000_000_000

        unit = "%" if unit_hint == "%" else "USD"

        figures.append(ExtractedFigure(
            value=value,
            unit=unit,
            name=label,
            source_loc=SourceLocation(
                doc_id=doc_id,
                page=page,
                table_or_figure="Document",
                row_col_or_line=label,
            ),
            confidence="high",
        ))

    return figures


def figure_extraction(state: FinancialAgentState) -> dict:
    """Extract figures from all documents."""
    from backend.document_ingest import get_document

    all_figures: list[ExtractedFigure] = []
    for doc_id in state.document_ids:
        doc = get_document(doc_id)
        if not doc:
            continue
        for chunk in doc.chunks:
            # Try LLM extraction first
            llm_figures = extract_figures_with_llm(chunk.content, doc_id, chunk.page, chunk.section)
            if llm_figures:
                all_figures.extend(llm_figures)
            else:
                # Fallback to regex
                figures = extract_figures_from_text(chunk.content, doc_id)
                for f in figures:
                    f.source_loc.page = chunk.page
                    f.source_loc.table_or_figure = chunk.section
                all_figures.extend(figures)

    return {"extracted_figures": all_figures}


# ---------------------------------------------------------------------------
# Node: Citation Indexing
# ---------------------------------------------------------------------------

def citation_indexing(state: FinancialAgentState) -> dict:
    """Build citation index from extracted figures."""
    index_map: dict[str, Citation] = {}

    for fig in state.extracted_figures:
        key = f"{fig.source_loc.doc_id}:{fig.source_loc.table_or_figure}"
        if key not in index_map:
            index_map[key] = Citation(
                doc_id=fig.source_loc.doc_id,
                section=fig.source_loc.table_or_figure,
                page=fig.source_loc.page,
                figure_refs=[],
            )
        if fig.name not in index_map[key].figure_refs:
            index_map[key].figure_refs.append(fig.name)

    return {"citation_index": list(index_map.values())}


# ---------------------------------------------------------------------------
# Node: Analyst Reasoning
# ---------------------------------------------------------------------------

def analyst_reasoning(state: FinancialAgentState) -> dict:
    """Draft initial response with figures and citations."""
    lines = []
    for fig in state.extracted_figures:
        if fig.confidence == "unverified":
            lines.append(f"- {fig.name}: [UNVERIFIED]")
        else:
            val = f"${fig.value:,.0f}" if fig.unit == "USD" else f"{fig.value}"
            anchor = f"(see {fig.source_loc.table_or_figure}, {fig.name}, p. {fig.source_loc.page})"
            lines.append(f"- {fig.name}: {val} {anchor}")

    response = "\n".join(lines) if lines else "No figures extracted from the provided documents."
    return {"final_response": response}


# ---------------------------------------------------------------------------
# Node: Computation
# ---------------------------------------------------------------------------

def computation(state: FinancialAgentState) -> dict:
    """Compute financial metrics from extracted figures."""
    computations: list[ComputationResult] = []
    fig_map: dict[str, ExtractedFigure] = {}
    for f in state.extracted_figures:
        if f.confidence != "unverified" and f.value is not None:
            fig_map[f.name] = f

    # Auto-detect common ratios
    current_assets = _find_figure(fig_map, ["Current Assets", "Total Current Assets"])
    current_liabilities = _find_figure(fig_map, ["Current Liabilities", "Total Current Liabilities"])
    revenue = _find_figure(fig_map, ["Revenue", "Total Revenue", "Net Revenue"])
    cogs = _find_figure(fig_map, ["Cost of Goods Sold", "COGS", "Cost of Sales"])
    gross_profit = _find_figure(fig_map, ["Gross Profit"])
    net_income = _find_figure(fig_map, ["Net Income", "Net Earnings"])

    # Current Ratio
    if current_assets and current_liabilities and current_liabilities.value:
        computations.append(execute_computation(
            formula="a / b",
            inputs={"a": current_assets.value, "b": current_liabilities.value},
            metric="Current Ratio",
            unit="ratio",
            sources={"a": current_assets, "b": current_liabilities},
        ))

    # Gross Margin
    if gross_profit and revenue and revenue.value:
        computations.append(execute_computation(
            formula="a / b",
            inputs={"a": gross_profit.value, "b": revenue.value},
            metric="Gross Margin",
            unit="ratio",
            sources={"a": gross_profit, "b": revenue},
        ))
    elif revenue and cogs and revenue.value:
        computations.append(execute_computation(
            formula="(a - b) / a",
            inputs={"a": revenue.value, "b": cogs.value},
            metric="Gross Margin",
            unit="ratio",
            sources={"a": revenue, "b": cogs},
        ))

    # Net Margin
    if net_income and revenue and revenue.value:
        computations.append(execute_computation(
            formula="a / b",
            inputs={"a": net_income.value, "b": revenue.value},
            metric="Net Margin",
            unit="ratio",
            sources={"a": net_income, "b": revenue},
        ))

    return {"computations": computations}


def _find_figure(fig_map: dict[str, ExtractedFigure], names: list[str]) -> ExtractedFigure | None:
    for name in names:
        if name in fig_map:
            return fig_map[name]
    return None


# ---------------------------------------------------------------------------
# Node: Anomaly Detection
# ---------------------------------------------------------------------------

def anomaly_detection(state: FinancialAgentState) -> dict:
    """Detect anomalies in figures and computations."""
    anomalies: list[Anomaly] = []

    # Materiality checks
    revenue = None
    for f in state.extracted_figures:
        if f.name.lower() in ("revenue", "total revenue", "net revenue") and f.value:
            revenue = f
            break

    if revenue and revenue.value:
        for f in state.extracted_figures:
            if f.value and f.unit == revenue.unit and f.name != revenue.name:
                ratio = abs(f.value) / revenue.value
                if ratio > settings.materiality_threshold:
                    severity = "critical" if ratio > 0.30 else "warning"
                    anomalies.append(Anomaly(
                        description=f"{f.name} is {ratio:.1%} of revenue",
                        severity=severity,
                        source=f.source_loc,
                        metric=f.name,
                        change_value=ratio,
                    ))

    # Computation-based anomalies
    for comp in state.computations:
        if comp.error or comp.result is None:
            continue
        # Check for extreme margin changes
        if comp.metric == "Gross Margin" and comp.result > 0.5:
            anomalies.append(Anomaly(
                description=f"Gross Margin is {comp.result:.1%} - unusually high",
                severity="warning",
                metric=comp.metric,
                change_value=comp.result,
            ))

    return {"anomalies": anomalies}


# ---------------------------------------------------------------------------
# Node: Response Assembly
# ---------------------------------------------------------------------------

def response_assembly(state: FinancialAgentState) -> dict:
    """Assemble final response with citations and anomaly observations."""
    parts = []

    # Figures
    if state.extracted_figures:
        parts.append("## Extracted Figures\n")
        for fig in state.extracted_figures:
            if fig.confidence == "unverified":
                parts.append(f"- **{fig.name}**: [UNVERIFIED]")
            else:
                val = f"${fig.value:,.0f}" if fig.unit == "USD" else f"{fig.value}"
                anchor = f"(see {fig.source_loc.table_or_figure}, p. {fig.source_loc.page})"
                parts.append(f"- **{fig.name}**: {val} {anchor}")

    # Computations
    if state.computations:
        parts.append("\n## Computed Metrics\n")
        for comp in state.computations:
            if comp.error:
                parts.append(f"- **{comp.metric}**: Error - {comp.error}")
            else:
                val = f"{comp.result:.2f}" if comp.result is not None else "N/A"
                parts.append(f"- **{comp.metric}**: {val} ({comp.formula})")

    # Anomalies
    if state.anomalies:
        parts.append("\n## Anomaly Observations\n")
        for anomaly in state.anomalies:
            badge = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(anomaly.severity, "")
            parts.append(f"- {badge} **[{anomaly.severity.upper()}]** {anomaly.description}")

    # Sources
    if state.citation_index:
        parts.append("\n## Sources\n")
        for cite in state.citation_index:
            parts.append(f"- [{cite.doc_id}] {cite.section} (p. {cite.page})")

    response = "\n".join(parts) if parts else "No analysis available."
    return {"final_response": response}


# ---------------------------------------------------------------------------
# Node: Guardrail Post-Check
# ---------------------------------------------------------------------------

def guardrail_post_check(state: FinancialAgentState) -> dict:
    """Scan response for advisory language and rewrite."""
    result = post_check_guardrail(state.final_response)
    return {
        "rewritten_response": result["rewritten_response"],
        "guardrail_interceptions": state.guardrail_interceptions + result["interceptions"],
        "final_response": result["rewritten_response"] if result["intercepted"] else state.final_response,
    }


# ---------------------------------------------------------------------------
# Node: Trade Tool
# ---------------------------------------------------------------------------

def should_offer_trade(state: FinancialAgentState) -> str:
    """Decide whether to offer trade tool."""
    if not settings.trade_tool_enabled:
        return "end"
    if state.user_query.strip().lower().startswith("/trade"):
        return "offer_trade"
    return "end"


def trade_tool(state: FinancialAgentState) -> dict:
    """Generate trade draft from analysis."""
    query = state.user_query
    parts = query.split()
    ticker = parts[1] if len(parts) > 1 else "UNKNOWN"
    direction = parts[2] if len(parts) > 2 else "long"

    if direction not in ("long", "short", "neutral"):
        direction = "long"

    # Synthesize thesis
    thesis_parts = []
    for fig in state.extracted_figures[:5]:
        if fig.value:
            thesis_parts.append(f"{fig.name}: ${fig.value:,.0f}")
    thesis = f"Based on analysis of {ticker}: {'; '.join(thesis_parts)}" if thesis_parts else f"Analysis of {ticker}"

    risk_flags = [a.description for a in state.anomalies if a.severity in ("warning", "critical")]

    draft = TradeDraft(
        ticker=ticker,
        direction=direction,
        thesis=thesis,
        risk_flags=risk_flags,
        timestamp=datetime.utcnow().isoformat(),
    )

    return {"trade_draft": draft}


def handle_trade_confirmation(state: FinancialAgentState) -> str:
    """Handle trade confirmation."""
    if state.trade_confirmed:
        return "confirm"
    return "end"


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

# Nodes in the order the graph runs them. Every node takes the state and
# returns a partial dict, which is what StateGraph merges back in.
PIPELINE_NODES: list[tuple[str, object]] = [
    ("guardrail_pre_check", guardrail_pre_check),
    ("figure_extraction", figure_extraction),
    ("citation_indexing", citation_indexing),
    ("computation", computation),
    ("anomaly_detection", anomaly_detection),
    ("response_assembly", response_assembly),
    ("guardrail_post_check", guardrail_post_check),
]


def build_financial_agent_graph():
    """Wire the analysis pipeline into a LangGraph StateGraph.

    Nodes run as a linear spine, then guardrail_post_check routes on
    should_offer_trade: a /trade query runs trade_tool, anything else ends.
    """
    graph = StateGraph(FinancialAgentState)

    for name, node in PIPELINE_NODES:
        graph.add_node(name, node)
    graph.add_node("trade_tool", trade_tool)

    graph.set_entry_point(PIPELINE_NODES[0][0])
    for (src, _), (dst, _) in zip(PIPELINE_NODES, PIPELINE_NODES[1:]):
        graph.add_edge(src, dst)

    graph.add_conditional_edges(
        "guardrail_post_check",
        should_offer_trade,
        {"offer_trade": "trade_tool", "end": END},
    )
    graph.add_edge("trade_tool", END)

    return graph.compile()


# Compiled once; the graph is stateless, so it is safe to share across requests.
financial_agent_graph = build_financial_agent_graph()
