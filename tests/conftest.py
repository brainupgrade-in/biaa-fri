"""
Shared fixtures for financial-report insight agent integration tests.
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_10k_content():
    """Minimal 10-K style content for testing."""
    return {
        "doc_id": "doc-001",
        "filename": "acme-10k-2024.pdf",
        "doc_type": "10-K",
        "company": "ACME Corp",
        "ticker": "ACME",
        "period": "FY2024",
        "currency": "USD",
        "pages": [
            {
                "page": 12,
                "section": "Income Statement",
                "tables": [
                    {
                        "name": "Consolidated Statements of Income",
                        "rows": [
                            {"label": "Revenue", "value": 5_200_000_000, "unit": "USD", "fy2024": 5_200_000_000, "fy2023": 4_800_000_000},
                            {"label": "Cost of Goods Sold", "value": 3_120_000_000, "unit": "USD", "fy2024": 3_120_000_000, "fy2023": 2_880_000_000},
                            {"label": "Gross Profit", "value": 2_080_000_000, "unit": "USD", "fy2024": 2_080_000_000, "fy2023": 1_920_000_000},
                            {"label": "Operating Expenses", "value": 1_040_000_000, "unit": "USD", "fy2024": 1_040_000_000, "fy2023": 960_000_000},
                            {"label": "Net Income", "value": 1_040_000_000, "unit": "USD", "fy2024": 1_040_000_000, "fy2023": 960_000_000},
                        ],
                    }
                ],
            },
            {
                "page": 14,
                "section": "Balance Sheet",
                "tables": [
                    {
                        "name": "Consolidated Balance Sheets",
                        "rows": [
                            {"label": "Current Assets", "value": 3_500_000_000, "unit": "USD"},
                            {"label": "Current Liabilities", "value": 1_750_000_000, "unit": "USD"},
                            {"label": "Total Assets", "value": 8_000_000_000, "unit": "USD"},
                            {"label": "Total Liabilities", "value": 4_000_000_000, "unit": "USD"},
                            {"label": "Shareholders Equity", "value": 4_000_000_000, "unit": "USD"},
                        ],
                    }
                ],
            },
            {
                "page": 16,
                "section": "Cash Flow Statement",
                "tables": [
                    {
                        "name": "Consolidated Statements of Cash Flows",
                        "rows": [
                            {"label": "Operating Cash Flow", "value": 1_200_000_000, "unit": "USD"},
                            {"label": "Capital Expenditures", "value": 400_000_000, "unit": "USD"},
                            {"label": "Free Cash Flow", "value": 800_000_000, "unit": "USD"},
                        ],
                    }
                ],
            },
            {
                "page": 45,
                "section": "Notes to Financial Statements",
                "tables": [],
                "narrative": "The Company changed its revenue recognition policy from ASC 605 to ASC 606...",
            },
        ],
    }


@pytest.fixture
def sample_figures():
    """Pre-extracted figures for testing."""
    return [
        {
            "value": 5_200_000_000,
            "unit": "USD",
            "name": "Revenue",
            "source_loc": {"doc_id": "doc-001", "page": 12, "table_or_figure": "Income Statement", "row_col_or_line": "Revenue"},
            "confidence": "high",
        },
        {
            "value": 4_800_000_000,
            "unit": "USD",
            "name": "Revenue FY2023",
            "source_loc": {"doc_id": "doc-001", "page": 12, "table_or_figure": "Income Statement", "row_col_or_line": "Revenue"},
            "confidence": "high",
        },
        {
            "value": 3_500_000_000,
            "unit": "USD",
            "name": "Current Assets",
            "source_loc": {"doc_id": "doc-001", "page": 14, "table_or_figure": "Balance Sheet", "row_col_or_line": "Current Assets"},
            "confidence": "high",
        },
        {
            "value": 1_750_000_000,
            "unit": "USD",
            "name": "Current Liabilities",
            "source_loc": {"doc_id": "doc-001", "page": 14, "table_or_figure": "Balance Sheet", "row_col_or_line": "Current Liabilities"},
            "confidence": "high",
        },
        {
            "value": 3_120_000_000,
            "unit": "USD",
            "name": "Cost of Goods Sold",
            "source_loc": {"doc_id": "doc-001", "page": 12, "table_or_figure": "Income Statement", "row_col_or_line": "Cost of Goods Sold"},
            "confidence": "high",
        },
        {
            "value": None,
            "unit": "USD",
            "name": "R&D Expense",
            "source_loc": {"doc_id": "doc-001", "page": 12, "table_or_figure": "Income Statement", "row_col_or_line": "R&D Expense"},
            "confidence": "unverified",
        },
    ]


@pytest.fixture
def sample_computations():
    """Pre-computed metrics for testing."""
    return [
        {
            "result": 2.0,
            "formula": "current_assets / current_liabilities",
            "inputs_with_sources": [
                {"value": 3_500_000_000, "unit": "USD", "name": "Current Assets", "confidence": "high"},
                {"value": 1_750_000_000, "unit": "USD", "name": "Current Liabilities", "confidence": "high"},
            ],
            "unit": "ratio",
            "metric": "Current Ratio",
            "error": None,
        },
        {
            "result": 0.40,
            "formula": "gross_profit / revenue",
            "inputs_with_sources": [
                {"value": 2_080_000_000, "unit": "USD", "name": "Gross Profit", "confidence": "high"},
                {"value": 5_200_000_000, "unit": "USD", "name": "Revenue", "confidence": "high"},
            ],
            "unit": "ratio",
            "metric": "Gross Margin",
            "error": None,
        },
        {
            "result": 8.33,
            "formula": "(rev_2024 - rev_2023) / rev_2023 * 100",
            "inputs_with_sources": [
                {"value": 5_200_000_000, "unit": "USD", "name": "Revenue FY2024", "confidence": "high"},
                {"value": 4_800_000_000, "unit": "USD", "name": "Revenue FY2023", "confidence": "high"},
            ],
            "unit": "%",
            "metric": "Revenue Growth YoY",
            "error": None,
        },
    ]


@pytest.fixture
def sample_anomalies():
    """Pre-detected anomalies for testing."""
    return [
        {
            "description": "Gross Margin expanded by 15 points",
            "severity": "warning",
            "source": {"doc_id": "doc-001", "page": 12, "table_or_figure": "Income Statement", "row_col_or_line": "Gross Profit"},
            "metric": "Gross Margin",
            "change_value": 15.0,
        },
        {
            "description": "Revenue changed by 8.33%",
            "severity": "info",
            "source": {"doc_id": "doc-001", "page": 12, "table_or_figure": "Income Statement", "row_col_or_line": "Revenue"},
            "metric": "Revenue Growth YoY",
            "change_value": 8.33,
        },
        {
            "description": "R&D Expense is 35% of revenue without disclosure",
            "severity": "critical",
            "source": {"doc_id": "doc-001", "page": 12, "table_or_figure": "Income Statement", "row_col_or_line": "R&D Expense"},
            "metric": "R&D Expense Ratio",
            "change_value": 0.35,
        },
    ]


@pytest.fixture
def sample_state(sample_figures, sample_computations, sample_anomalies):
    """Full agent state for testing."""
    return {
        "user_query": "What was ACME's revenue and current ratio?",
        "document_ids": ["doc-001"],
        "extracted_figures": sample_figures,
        "citation_index": [
            {"doc_id": "doc-001", "section": "Income Statement", "page": 12, "figure_refs": ["Revenue", "COGS", "Gross Profit"]},
            {"doc_id": "doc-001", "section": "Balance Sheet", "page": 14, "figure_refs": ["Current Assets", "Current Liabilities"]},
        ],
        "computations": sample_computations,
        "anomalies": sample_anomalies,
        "guardrail_interceptions": [],
        "rewritten_response": None,
        "trade_draft": None,
        "trade_confirmed": False,
        "final_response": "",
    }


@pytest.fixture
def advisory_responses():
    """Responses containing advisory language for guardrail testing."""
    return [
        "You should buy ACME stock immediately.",
        "I recommend selling your position in ACME.",
        "The stock is likely to outperform the market.",
        "You should hold your current position.",
        "Consider overweighting this stock in your portfolio.",
        "The stock looks like a sell at current levels.",
        "I advise you to reduce your exposure.",
        "This is a strong buy recommendation.",
    ]


@pytest.fixture
def observational_responses():
    """Responses that are purely observational (no advisory language)."""
    return [
        "ACME's revenue grew 8.33% YoY to $5.2 billion.",
        "The current ratio of 2.0 indicates adequate liquidity.",
        "Gross margin expanded by 15 points to 40%.",
        "The company reported net income of $1.04 billion.",
        "Free cash flow was $800 million for the period.",
        "Total assets increased to $8 billion.",
    ]


@pytest.fixture
def trade_requests():
    """Sample trade requests for testing."""
    return [
        {"ticker": "ACME", "direction": "long"},
        {"ticker": "ACME", "direction": "short"},
        {"ticker": "XYZ", "direction": "long"},
    ]


# ---------------------------------------------------------------------------
# Mock fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm():
    """Mock LLM for testing without API calls."""
    llm = Mock()
    llm.invoke = AsyncMock()
    llm.ainvoke = AsyncMock()
    return llm


@pytest.fixture
def mock_vector_store():
    """Mock vector store for testing."""
    store = Mock()
    store.similarity_search = Mock(return_value=[])
    store.add_documents = Mock()
    return store


@pytest.fixture
def mock_database():
    """Mock database for testing."""
    db = Mock()
    db.execute = AsyncMock()
    db.fetch_all = AsyncMock(return_value=[])
    db.fetch_one = AsyncMock(return_value=None)
    return db


# ---------------------------------------------------------------------------
# Async fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
