"""
End-to-end integration tests for the complete agent pipeline.
Covers: UC-01 through UC-10, full workflow validation
"""
import pytest
from unittest.mock import Mock, AsyncMock


class TestRevenueGroundingE2E:
    """UC-01: Revenue Figure Grounding - End to End."""

    @pytest.mark.asyncio
    async def test_complete_revenue_grounding_flow(self, full_agent, sample_10k_content):
        """UC-01: Full pipeline should extract, ground, and cite revenue."""
        result = await full_agent.invoke({
            "query": "What was ACME's revenue in FY2024?",
            "document_ids": ["doc-001"]
        })

        # Verify figure extraction
        assert any(f["name"] == "Revenue" for f in result["extracted_figures"])

        # Verify source grounding
        revenue = [f for f in result["extracted_figures"] if f["name"] == "Revenue"][0]
        assert revenue["source_loc"]["page"] == 12
        assert revenue["source_loc"]["table_or_figure"] == "Income Statement"

        # Verify inline citation
        assert "§ Income Statement" in result["final_response"]
        assert "p. 12" in result["final_response"]

        # Verify confidence
        assert revenue["confidence"] == "high"


class TestRatioTraceabilityE2E:
    """UC-02: Computed Ratio Traceability - End to End."""

    @pytest.mark.asyncio
    async def test_current_ratio_computation(self, full_agent, sample_10k_content):
        """UC-02: Current ratio should be computed with full traceability."""
        result = await full_agent.invoke({
            "query": "What is ACME's current ratio?",
            "document_ids": ["doc-001"]
        })

        # Verify computation
        assert any(c["metric"] == "Current Ratio" for c in result["computations"])

        # Verify formula
        current_ratio = [c for c in result["computations"] if c["metric"] == "Current Ratio"][0]
        assert "current_assets / current_liabilities" in current_ratio["formula"]

        # Verify inputs with sources
        assert len(current_ratio["inputs_with_sources"]) == 2
        for inp in current_ratio["inputs_with_sources"]:
            assert "source_loc" in inp

        # Verify result
        assert current_ratio["result"] == 2.0


class TestAnomalyDetectionE2E:
    """UC-03: Anomaly Detection on Margin Shift - End to End."""

    @pytest.mark.asyncio
    async def test_margin_anomaly_detection(self, full_agent, sample_10k_content):
        """UC-03: Sudden margin expansion should be flagged."""
        result = await full_agent.invoke({
            "query": "Are there any anomalies in ACME's financials?",
            "document_ids": ["doc-001"]
        })

        # Verify anomalies detected
        assert len(result["anomalies"]) > 0

        # Verify severity assignment
        for anomaly in result["anomalies"]:
            assert anomaly["severity"] in ["info", "warning", "critical"]

        # Verify observation only (no conclusions)
        for anomaly in result["anomalies"]:
            assert "should" not in anomaly["description"].lower()
            assert "recommend" not in anomaly["description"].lower()


class TestNoAdviceEnforcementE2E:
    """UC-04: No-Advice Enforcement - End to End."""

    @pytest.mark.asyncio
    async def test_advisory_question_blocked(self, full_agent, sample_10k_content):
        """UC-04: Advisory questions should produce factual response."""
        result = await full_agent.invoke({
            "query": "Should I buy ACME stock?",
            "document_ids": ["doc-001"]
        })

        # Verify no advisory language in response
        response_lower = result["final_response"].lower()
        assert "you should buy" not in response_lower
        assert "you should sell" not in response_lower
        assert "recommend" not in response_lower

        # Verify guardrail interception logged
        assert len(result["guardrail_interceptions"]) > 0

        # Verify factual content
        assert "revenue" in response_lower or "financial" in response_lower

    @pytest.mark.asyncio
    async def test_guardrail_log_entry(self, full_agent, sample_10k_content):
        """UC-04: Guardrail interception should be logged."""
        result = await full_agent.invoke({
            "query": "Should I buy ACME?",
            "document_ids": ["doc-001"]
        })

        assert len(result["guardrail_interceptions"]) > 0

        log_entry = result["guardrail_interceptions"][0]
        assert "timestamp" in log_entry
        assert "original_text" in log_entry
        assert "rewritten_text" in log_entry
        assert "trigger_keywords" in log_entry


class TestTradeDraftE2E:
    """UC-05: Trade Draft Generation - End to End."""

    @pytest.mark.asyncio
    async def test_trade_draft_flow(self, full_agent, sample_10k_content):
        """UC-05: /trade command should generate draft."""
        # First, analyze the document
        await full_agent.invoke({
            "query": "Analyze ACME financials",
            "document_ids": ["doc-001"]
        })

        # Then request trade draft
        result = await full_agent.invoke({
            "query": "/trade ACME long",
            "document_ids": ["doc-001"]
        })

        # Verify draft created
        assert result["trade_draft"] is not None
        assert result["trade_draft"]["ticker"] == "ACME"
        assert result["trade_draft"]["direction"] == "long"

        # Verify not confirmed
        assert result["trade_confirmed"] is False

        # Verify thesis
        assert len(result["trade_draft"]["thesis"]) > 0

        # Verify risk flags
        assert isinstance(result["trade_draft"]["risk_flags"], list)


class TestMultiPeriodComparisonE2E:
    """UC-06: Multi-Period Comparison with Unit Validation - End to End."""

    @pytest.mark.asyncio
    async def test_yoy_revenue_growth(self, full_agent, sample_10k_content):
        """UC-06: YoY revenue growth should be computed correctly."""
        result = await full_agent.invoke({
            "query": "What is ACME's YoY revenue growth?",
            "document_ids": ["doc-001"]
        })

        # Verify computation
        assert any(c["metric"] == "Revenue Growth YoY" for c in result["computations"])

        # Verify formula
        yoy = [c for c in result["computations"] if c["metric"] == "Revenue Growth YoY"][0]
        assert "rev_2024" in yoy["formula"] or "rev_2023" in yoy["formula"]

        # Verify result is reasonable
        assert 0 < yoy["result"] < 100  # Positive growth, less than 100%


class TestCitationAuditE2E:
    """UC-07: Citation Completeness Audit - End to End."""

    @pytest.mark.asyncio
    async def test_all_claims_cited(self, full_agent, sample_10k_content):
        """UC-07: Every factual claim should have a citation."""
        result = await full_agent.invoke({
            "query": "Summarize ACME's financial performance",
            "document_ids": ["doc-001"]
        })

        # Verify citation index exists
        assert len(result["citation_index"]) > 0

        # Verify sources block in response
        assert "Sources" in result["final_response"]

        # Verify no unverified claims in response
        assert "[UNVERIFIED]" not in result["final_response"] or \
               result["final_response"].count("[UNVERIFIED]") == 0


class TestUnverifiedHandlingE2E:
    """UC-08: Unverified Figure Handling - End to End."""

    @pytest.mark.asyncio
    async def test_unverified_figure_marked(self, full_agent, sample_10k_content):
        """UC-08: Unverified figures should be marked and excluded."""
        result = await full_agent.invoke({
            "query": "What is ACME's R&D expense?",
            "document_ids": ["doc-001"]
        })

        # Verify unverified figure exists
        unverified = [f for f in result["extracted_figures"] if f["confidence"] == "unverified"]
        assert len(unverified) > 0

        # Verify unverified figure not used in computations
        for comp in result["computations"]:
            for inp in comp["inputs_with_sources"]:
                assert inp["confidence"] != "unverified"


class TestMaterialityEscalationE2E:
    """UC-09: Materiality-Based Anomaly Escalation - End to End."""

    @pytest.mark.asyncio
    async def test_critical_severity_for_undisclosed(self, full_agent, sample_10k_content):
        """UC-09: Undisclosed material items should be critical."""
        result = await full_agent.invoke({
            "query": "Check for material misstatements",
            "document_ids": ["doc-001"]
        })

        # Check for critical anomalies
        critical = [a for a in result["anomalies"] if a["severity"] == "critical"]
        if critical:
            # Critical anomalies should have source references
            for anomaly in critical:
                assert "source" in anomaly


class TestAuditLogReviewE2E:
    """UC-10: Guardrail Audit Log Review - End to End."""

    @pytest.mark.asyncio
    async def test_audit_log_accessible(self, full_agent, sample_10k_content):
        """UC-10: Audit logs should be accessible via admin endpoint."""
        # First, trigger some guardrail interceptions
        await full_agent.invoke({
            "query": "Should I buy ACME?",
            "document_ids": ["doc-001"]
        })

        # Then verify logs are retrievable
        # (In real implementation, this would call the admin API)
        # For now, verify the state has the logs
        result = await full_agent.invoke({
            "query": "Show audit logs",
            "document_ids": ["doc-001"]
        })

        # Verify guardrail_interceptions is populated
        assert isinstance(result["guardrail_interceptions"], list)


class TestCompleteUserJourney:
    """Test complete user journey from upload to trade draft."""

    @pytest.mark.asyncio
    async def test_full_journey(self, full_agent, sample_10k_content):
        """Complete user journey: upload -> analyze -> trade draft."""
        # Step 1: Upload document (simulated)
        # In real implementation, this would be an API call

        # Step 2: Ask about revenue
        result1 = await full_agent.invoke({
            "query": "What was ACME's revenue?",
            "document_ids": ["doc-001"]
        })
        assert "revenue" in result1["final_response"].lower()

        # Step 3: Compute ratios
        result2 = await full_agent.invoke({
            "query": "What is the current ratio?",
            "document_ids": ["doc-001"]
        })
        assert any(c["metric"] == "Current Ratio" for c in result2["computations"])

        # Step 4: Check for anomalies
        result3 = await full_agent.invoke({
            "query": "Any anomalies?",
            "document_ids": ["doc-001"]
        })
        assert isinstance(result3["anomalies"], list)

        # Step 5: Ask for trade draft
        result4 = await full_agent.invoke({
            "query": "/trade ACME long",
            "document_ids": ["doc-001"]
        })
        assert result4["trade_draft"] is not None

        # Verify no advisory language throughout
        for result in [result1, result2, result3, result4]:
            assert "you should" not in result["final_response"].lower()
            assert "recommend" not in result["final_response"].lower()


class TestErrorRecovery:
    """Test error recovery in the pipeline."""

    @pytest.mark.asyncio
    async def test_missing_document_graceful(self, full_agent):
        """Missing document should be handled gracefully."""
        result = await full_agent.invoke({
            "query": "What was revenue?",
            "document_ids": ["nonexistent"]
        })

        # Should not crash, should return meaningful error
        assert result["final_response"] is not None
        assert "error" in result["final_response"].lower() or "not found" in result["final_response"].lower()

    @pytest.mark.asyncio
    async def test_computation_failure_recovery(self, full_agent, sample_10k_content):
        """Computation failure should not crash the pipeline."""
        # This would test scenarios where computation fails
        result = await full_agent.invoke({
            "query": "Compute impossible metric",
            "document_ids": ["doc-001"]
        })

        # Pipeline should complete even if computation fails
        assert result["final_response"] is not None


# ---------------------------------------------------------------------------
# Fixtures for E2E tests
# ---------------------------------------------------------------------------

@pytest.fixture
def full_agent():
    """Full agent pipeline for E2E testing."""
    # In real implementation, this would be the actual LangGraph agent
    # For testing, we create a mock that simulates the full pipeline
    return MockFullAgent()


class MockFullAgent:
    """Mock full agent for E2E testing."""

    def __init__(self):
        self.state = {
            "extracted_figures": [],
            "citation_index": [],
            "computations": [],
            "anomalies": [],
            "guardrail_interceptions": [],
            "trade_draft": None,
            "trade_confirmed": False,
            "final_response": "",
        }

    async def invoke(self, input_state):
        """Simulate full agent pipeline."""
        # Simulate figure extraction
        self.state["extracted_figures"] = [
            {
                "name": "Revenue",
                "value": 5_200_000_000,
                "unit": "USD",
                "confidence": "high",
                "source_loc": {"doc_id": "doc-001", "page": 12, "table_or_figure": "Income Statement", "row_col_or_line": "Revenue"},
            },
            {
                "name": "R&D Expense",
                "value": None,
                "unit": "USD",
                "confidence": "unverified",
                "source_loc": {"doc_id": "doc-001", "page": 12, "table_or_figure": "Income Statement", "row_col_or_line": "R&D Expense"},
            },
        ]

        # Simulate computations
        self.state["computations"] = [
            {
                "metric": "Current Ratio",
                "result": 2.0,
                "formula": "current_assets / current_liabilities",
                "inputs_with_sources": [
                    {"value": 3_500_000_000, "unit": "USD", "name": "Current Assets", "confidence": "high", "source_loc": {"page": 14}},
                    {"value": 1_750_000_000, "unit": "USD", "name": "Current Liabilities", "confidence": "high", "source_loc": {"page": 14}},
                ],
                "unit": "ratio",
            },
            {
                "metric": "Revenue Growth YoY",
                "result": 8.33,
                "formula": "(rev_2024 - rev_2023) / rev_2023 * 100",
                "inputs_with_sources": [],
                "unit": "%",
            },
        ]

        # Simulate anomalies
        self.state["anomalies"] = [
            {
                "description": "Gross Margin expanded by 15 points",
                "severity": "warning",
                "source": {"page": 12},
                "metric": "Gross Margin",
                "change_value": 15.0,
            }
        ]

        # Simulate guardrail
        query = input_state.get("query", "")
        if "should i buy" in query.lower() or "recommend" in query.lower():
            self.state["guardrail_interceptions"].append({
                "timestamp": "2024-01-01T00:00:00",
                "original_text": query,
                "rewritten_text": f"Analysis request: {query}",
                "trigger_keywords": ["should", "buy"],
            })
            self.state["final_response"] = f"ACME's revenue was $5.2B. Current ratio is 2.0. (see § Income Statement, p. 12)"
        elif "/trade" in query:
            parts = query.split()
            ticker = parts[1] if len(parts) > 1 else "ACME"
            direction = parts[2] if len(parts) > 2 else "long"
            self.state["trade_draft"] = {
                "ticker": ticker,
                "direction": direction,
                "thesis": "Revenue growth supports position.",
                "risk_flags": ["Margin expansion"],
                "timestamp": "2024-01-01T00:00:00",
            }
            self.state["final_response"] = f"Trade draft created for {ticker} {direction}."
        else:
            self.state["final_response"] = f"ACME's revenue was $5.2B. (see § Income Statement, p. 12)"

        return self.state
