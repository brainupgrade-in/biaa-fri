# Financial-Report Insight Agent — Requirements & Use Cases

**Objective:** Build an LLM-powered agent that ingests financial reports, extracts and grounds every figure to its source document, cites claims, performs safe computations, flags anomalies, enforces a no-advice guardrail, and exposes a withheld trade tool that assists users without acting autonomously.

---

## 1. Core Capabilities

| # | Capability | Description |
|---|------------|-------------|
| C1 | Source Grounding | Every numerical figure the agent emits must trace back to a specific location (page, table, footnote) in the source document. |
| C2 | Claim Citation | Every qualitative or quantitative claim must carry a verifiable citation (document ID + section/table ref). |
| C3 | Safe Computation | Derived figures (ratios, deltas, aggregates) are computed by a deterministic module, not by the LLM; the LLM only formats and explains. |
| C4 | Anomaly Flagging | Statistical outliers, material misstatements, unusual period-over-period changes, or GAAP/IFRS red-flags are surfaced with severity levels. |
| C5 | No-Advice Guardrail | The agent must never recommend a specific action (buy, sell, hold, etc.). It may present facts and observations; it may never advise. |
| C6 | Withheld Trade Tool | A trade-idea generation module exists but is locked behind user confirmation. It produces assistive drafts, never executes autonomously. |

---

## 2. Detailed Specifications

### 2.1 — Source Grounding (C1)

- **F-GND-01** — Every extracted number is stored as a `(value, unit, source_loc)` tuple where `source_loc = { doc_id, page, table_or_figure, row_col_or_line }`.
- **F-GND-02** — When the agent references a figure in its response it must render an inline anchor, e.g. `(see § Income Statement, line: Revenue, p. 12)`.
- **F-GND-03** — If a figure cannot be located in the source, the agent emits `[UNVERIFIED]` and refuses to use it in downstream computations.
- **F-GND-04** — A grounding confidence score (high / medium / low / unverified) is attached to every extracted figure and propagated to any derived figure that uses it.

### 2.2 — Claim Citation (C2)

- **F-CIT-01** — Every sentence in the agent output that contains a factual claim must end with a citation block: `[{doc_id} § section, p. N]`.
- **F-CIT-02** — The agent maintains a citation index; at the end of each response it emits a "Sources" block listing every referenced document + section.
- **F-CIT-03** — If the agent synthesizes a claim from multiple sources, all contributing sources must be listed.
- **F-CIT-04** — Hallucination detection: the agent self-checks each claim against the citation index before outputting. Claims without a matching citation are suppressed.

### 2.3 — Safe Computation (C3)

- **F-CMP-01** — All arithmetic is delegated to a sandboxed computation module (Python / WASM). The LLM never computes.
- **F-CMP-02** — The computation module returns `{ result, formula, inputs_with_sources }`. The LLM formats the explanation.
- **F-CMP-03** — Precision policy: percentages to 2 dp, currency to nearest whole unit unless sub-unit precision is present in source.
- **F-CMP-04** — Division-by-zero and overflow guard: the module returns a symbolic error rather than `inf` / `NaN`.
- **F-CMP-05** — Unit consistency check: the module validates that all inputs share compatible units before operating.
- **F-CMP-06** — Temporal consistency check: the module verifies that all inputs reference the same reporting period unless the operation is explicitly a period-over-period comparison.

### 2.4 — Anomaly Flagging (C4)

- **F-ANM-01** — Outlier detection: flag any figure whose period-over-period change exceeds a configurable z-score threshold (default: |z| > 2).
- **F-ANM-02** — Materiality threshold: flag any single line item that exceeds a configurable % of total revenue (default: 10%).
- **F-ANM-03** — GAAP/IFRS red-flag heuristics: sudden changes in accounting policy without disclosure, unqualified audit with going-concern notes, related-party transactions above materiality.
- **F-ANM-04** — Each anomaly is assigned a severity: `info`, `warning`, `critical`.
- **F-ANM-05** — The agent must not draw conclusions from anomalies; it states the observation and severity only.

### 2.5 — No-Advice Guardrail (C5)

- **F-GRD-01** — A classifier (keyword + LLM self-check) scans the agent's final response for advisory language ("you should", "recommend", "buy", "sell", "hold", "overweight", "underweight", "outperform", etc.).
- **F-GRD-02** — If advisory language is detected, the offending sentence is rewritten to be observational: "Company X's revenue declined 25% YoY" instead of "You should sell Company X".
- **F-GRD-03** — The guardrail logs every intercepted advisory attempt for auditability.
- **F-GRD-04** — A system-level prompt hard-constraint is injected: "You are an analysis agent. You must never recommend actions."

### 2.6 — Withheld Trade Tool (C6)

- **F-TRD-01** — The trade tool accepts a structured brief `{ ticker, thesis, direction (long/short/neutral), risk_flags }` generated by the analysis agent.
- **F-TRD-02** — The trade tool is disabled by default. It only activates when the user explicitly invokes it (e.g., `/trade` command).
- **F-TRD-03** — Before execution, the tool presents a confirmation card showing: ticker, proposed direction, supporting thesis, risk flags, and a "Confirm / Cancel" prompt.
- **F-TRD-04** — The tool NEVER executes a real order. It generates a trade draft that the user must manually submit through their brokerage.
- **F-TRD-05** — All trade drafts are logged with timestamps for compliance.
- **F-TRD-06** — The trade tool is assistive only: it may suggest position sizing based on user-configured risk parameters, but the user sets the final parameters.

---

## 3. Trackable Use Cases

### UC-01: Revenue Figure Grounding
**As a** financial analyst,  
**I want** every revenue figure cited by the agent to point to the exact table cell in the 10-K,  
**So that** I can verify accuracy before presenting to stakeholders.  

**Acceptance Criteria:**
- [ ] Agent extracts Revenue from income statement with `(value, unit, source_loc)`.
- [ ] Response includes inline anchor `(see § Income Statement, Revenue, p. N)`.
- [ ] `confidence: high` when the figure is in a primary table.

**Priority:** P0 — Critical

---

### UC-02: Computed Ratio Traceability
**As a** portfolio manager,  
**I want** the agent to compute the current ratio and show me the formula, inputs, and source locations for each input,  
**So that** I can audit the computation independently.  

**Acceptance Criteria:**
- [ ] Agent delegates `current_assets / current_liabilities` to the computation module.
- [ ] Output includes: formula, input values with sources, result.
- [ ] Division-by-zero guard triggers if liabilities = 0.

**Priority:** P0 — Critical

---

### UC-03: Anomaly Detection on Sudden Margin Shift
**As a** risk officer,  
**I want** the agent to flag a sudden 15-point gross margin expansion with a `warning` severity,  
**So that** I can investigate potential accounting irregularities.  

**Acceptance Criteria:**
- [ ] Agent detects period-over-period change > z-score threshold.
- [ ] Flags as `warning` (not `critical` unless additional red-flags present).
- [ ] Agent does not speculate on the cause; states the observation only.

**Priority:** P1 — High

---

### UC-04: No-Advice Enforcement
**As a** compliance officer,  
**I want** the agent to never emit advisory language, even if the user explicitly asks "should I buy X?",  
**So that** the system avoids regulatory liability.  

**Acceptance Criteria:**
- [ ] User asks "Should I buy ACME?"
- [ ] Agent responds with facts: valuation metrics, risk flags, anomalies — but no recommendation.
- [ ] Guardrail log shows the interception event.

**Priority:** P0 — Critical

---

### UC-05: Trade Draft Generation (Assistive)
**As a** trader,  
**I want** to request a trade draft after the agent's analysis, review its thesis and risk flags, and then manually submit the order,  
**So that** I retain full control over execution.  

**Acceptance Criteria:**
- [ ] User issues `/trade ACME long`.
- [ ] Agent generates draft with `{ ticker, direction, thesis, risk_flags }`.
- [ ] Confirmation card is displayed; no order is placed.
- [ ] Draft is logged with timestamp.

**Priority:** P2 — Medium

---

### UC-06: Multi-Period Comparison with Unit Validation
**As a** financial analyst,  
**I want** the agent to compute YoY revenue growth and validate that both periods use the same currency and reporting standard,  
**So that** the comparison is meaningful.  

**Acceptance Criteria:**
- [ ] Agent extracts revenue for FY2024 and FY2023.
- [ ] Computation module validates unit consistency (USD vs. USD).
- [ ] Output includes: `(Rev_2024 - Rev_2023) / Rev_2023`, both inputs with sources.

**Priority:** P1 — High

---

### UC-07: Citation Completeness Audit
**As a** QA engineer,  
**I want** every factual claim in the agent's response to have at least one citation,  
**So that** I can verify there are no unsupported assertions.  

**Acceptance Criteria:**
- [ ] Agent self-checks claims against citation index before output.
- [ ] Unverifiable claims are suppressed, not emitted.
- [ ] End-of-response "Sources" block lists all referenced documents and sections.

**Priority:** P1 — High

---

### UC-08: Unverified Figure Handling
**As a** financial analyst,  
**I want** the agent to mark figures it cannot locate in the source as `[UNVERIFIED]` and exclude them from computations,  
**So that** I know exactly what data is reliable and what is not.  

**Acceptance Criteria:**
- [ ] Agent attempts to extract a figure not present in the PDF.
- [ ] Agent emits `[UNVERIFIED]` tag.
- [ ] Computation module rejects inputs with `confidence: unverified`.

**Priority:** P0 — Critical

---

### UC-09: Materiality-Based Anomaly Escalation
**As a** CFO,  
**I want** the agent to escalate to `critical` severity any single expense line that exceeds 30% of total revenue without prior disclosure,  
**So that** I can address potential misstatement before filing.  

**Acceptance Criteria:**
- [ ] Agent detects line item > 30% of revenue.
- [ ] Agent checks disclosure notes for prior-period mention.
- [ ] If undisclosed, severity = `critical`.

**Priority:** P1 — High

---

### UC-10: Guardrail Audit Log Review
**As a** compliance officer,  
**I want** to review a log of every advisory attempt intercepted by the guardrail, including the original text and the rewritten output,  
**So that** I can audit the system's behavior over time.  

**Acceptance Criteria:**
- [ ] Each interception record includes: timestamp, original sentence, rewritten sentence, trigger keyword.
- [ ] Logs are append-only and tamper-evident.
- [ ] Logs are accessible via admin endpoint.

**Priority:** P1 — High

---

## 4. Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-01 | Latency per query (extract + compute + respond) | < 8 seconds (p95) |
| NFR-02 | Source grounding accuracy | ≥ 95% of figures traceable |
| NFR-03 | False-positive rate for anomaly flags | ≤ 10% |
| NFR-04 | Guardrail recall (advisory language caught) | ≥ 99% |
| NFR-05 | Audit log retention | 7 years |
| NFR-06 | Supported document formats | PDF, HTML, XBRL |
| NFR-07 | Concurrent user sessions | ≥ 100 |

---

## 5. Architecture Sketch

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  User Input  │────▶│  Guardrail   │────▶│  LLM Analyst    │
│  (question)  │     │  Pre-Check   │     │  (with prompts) │
└─────────────┘     └──────────────┘     └────────┬────────┘
                                                   │
                                       ┌───────────▼───────────┐
                                       │   Source Grounding     │
                                       │   Engine               │
                                       │  (extract + cite)      │
                                       └───────────┬───────────┘
                                                   │
                                       ┌───────────▼───────────┐
                                       │   Computation Module   │
                                       │   (deterministic)      │
                                       └───────────┬───────────┘
                                                   │
                                       ┌───────────▼───────────┐
                                       │   Anomaly Detector     │
                                       │   (statistical + rules)│
                                       └───────────┬───────────┘
                                                   │
                                       ┌───────────▼───────────┐
                                       │   Guardrail Post-Check │
                                       │   (advisory filter)    │
                                       └───────────┬───────────┘
                                                   │
                                                   ▼
                                        ┌─────────────────┐
                                        │   Agent Response │
                                        └────────┬────────┘
                                                 │
                                        (optional)│
                                                 ▼
                                        ┌─────────────────┐
                                        │  Trade Tool      │
                                        │  (user-invoked)  │
                                        │  Draft + Confirm │
                                        └─────────────────┘
```

---

## 6. Out of Scope (v1)

- Real-time market data feeds
- Portfolio-level aggregation across multiple filings
- Natural language querying of proprietary databases
- Automated order execution
- Multi-language support (English only v1)
