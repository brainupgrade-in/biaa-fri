"""
Integration tests for REST API endpoints.
Covers: API layer for all features
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient


class TestDocumentEndpoints:
    """Test document management endpoints."""

    @pytest.mark.asyncio
    async def test_upload_document(self, client, sample_pdf_file):
        """POST /api/documents/upload should accept document upload."""
        response = await client.post(
            "/api/documents/upload",
            files={"file": ("test-10k.pdf", sample_pdf_file, "application/pdf")}
        )
        assert response.status_code == 200
        data = response.json()
        assert "doc_id" in data
        assert data["status"] == "processing"

    @pytest.mark.asyncio
    async def test_get_document(self, client, mock_db):
        """GET /api/documents/{doc_id} should return document metadata."""
        mock_db.fetch_one.return_value = {
            "id": "doc-001",
            "filename": "acme-10k.pdf",
            "doc_type": "10-K",
        }

        response = await client.get("/api/documents/doc-001")
        assert response.status_code == 200
        data = response.json()
        assert data["doc_id"] == "doc-001"

    @pytest.mark.asyncio
    async def test_get_document_not_found(self, client, mock_db):
        """GET /api/documents/{doc_id} should return 404 for missing doc."""
        mock_db.fetch_one.return_value = None

        response = await client.get("/api/documents/nonexistent")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_documents(self, client, mock_db):
        """GET /api/documents should list all documents."""
        mock_db.fetch_all.return_value = [
            {"id": "doc-001", "filename": "acme-10k.pdf"},
            {"id": "doc-002", "filename": "xyz-10k.pdf"},
        ]

        response = await client.get("/api/documents")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


class TestAnalysisEndpoints:
    """Test analysis endpoints."""

    @pytest.mark.asyncio
    async def test_query_analysis(self, client, mock_agent):
        """POST /api/analysis/query should return analysis results."""
        mock_agent.invoke.return_value = {
            "final_response": "ACME's revenue was $5.2B.",
            "citations": [{"doc_id": "doc-001", "section": "Income Statement", "page": 12}],
            "anomalies": [],
            "computations": [],
        }

        response = await client.post(
            "/api/analysis/query",
            json={"query": "What was ACME's revenue?", "document_ids": ["doc-001"]}
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "citations" in data

    @pytest.mark.asyncio
    async def test_query_analysis_missing_query(self, client):
        """POST /api/analysis/query should reject missing query."""
        response = await client.post(
            "/api/analysis/query",
            json={"document_ids": ["doc-001"]}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_query_analysis_empty_documents(self, client):
        """POST /api/analysis/query should reject empty document list."""
        response = await client.post(
            "/api/analysis/query",
            json={"query": "What was revenue?", "document_ids": []}
        )
        assert response.status_code == 422


class TestTradeEndpoints:
    """Test trade tool endpoints."""

    @pytest.mark.asyncio
    async def test_create_trade_draft(self, client, mock_agent):
        """POST /api/trade/draft should generate trade draft."""
        mock_agent.invoke.return_value = {
            "trade_draft": {
                "ticker": "ACME",
                "direction": "long",
                "thesis": "Revenue growth supports long position.",
                "risk_flags": ["Margin expansion"],
            }
        }

        response = await client.post(
            "/api/trade/draft",
            json={"ticker": "ACME", "direction": "long"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "ACME"
        assert data["direction"] == "long"

    @pytest.mark.asyncio
    async def test_confirm_trade(self, client, mock_db):
        """POST /api/trade/confirm/{draft_id} should log confirmation."""
        mock_db.fetch_one.return_value = {"id": "draft-001", "ticker": "ACME"}

        response = await client.post("/api/trade/confirm/draft-001")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_confirm_trade_not_found(self, client, mock_db):
        """POST /api/trade/confirm/{draft_id} should return 404 for missing draft."""
        mock_db.fetch_one.return_value = None

        response = await client.post("/api/trade/confirm/nonexistent")
        assert response.status_code == 404


class TestAuditEndpoints:
    """Test compliance and audit endpoints."""

    @pytest.mark.asyncio
    async def test_get_guardrail_logs(self, client, mock_db):
        """GET /api/audit/guardrail-logs should return interception logs."""
        mock_db.fetch_all.return_value = [
            {
                "timestamp": "2024-01-01T10:00:00",
                "original_text": "You should buy ACME.",
                "rewritten_text": "ACME is under consideration.",
                "trigger_keywords": ["should", "buy"],
            }
        ]

        response = await client.get(
            "/api/audit/guardrail-logs",
            params={"start_date": "2024-01-01", "end_date": "2024-01-02"}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    @pytest.mark.asyncio
    async def test_get_trade_drafts(self, client, mock_db):
        """GET /api/audit/trade-drafts should return draft history."""
        mock_db.fetch_all.return_value = [
            {"ticker": "ACME", "direction": "long", "created_at": "2024-01-01T10:00:00"}
        ]

        response = await client.get("/api/audit/trade-drafts", params={"user_id": "user-001"})
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1


class TestAdminEndpoints:
    """Test admin endpoints."""

    @pytest.mark.asyncio
    async def test_system_health(self, client, mock_db):
        """GET /api/admin/system-health should return system status."""
        mock_db.fetch_one.return_value = {"result": 1}

        response = await client.get("/api/admin/system-health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"


class TestErrorHandling:
    """Test API error handling."""

    @pytest.mark.asyncio
    async def test_internal_server_error(self, client, mock_agent):
        """Internal errors should return 500 with error message."""
        mock_agent.invoke.side_effect = Exception("LLM API error")

        response = await client.post(
            "/api/analysis/query",
            json={"query": "test", "document_ids": ["doc-001"]}
        )
        assert response.status_code == 500
        data = response.json()
        assert "error" in data

    @pytest.mark.asyncio
    async def test_validation_error(self, client):
        """Invalid input should return 422."""
        response = await client.post(
            "/api/analysis/query",
            json={"invalid": "data"}
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Fixtures for API tests
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Create test client."""
    # In real implementation, this would import the FastAPI app
    # from backend.main import app
    # return TestClient(app)
    return TestClient(Mock())


@pytest.fixture
def sample_pdf_file():
    """Create sample PDF file for upload testing."""
    return b"%PDF-1.4 fake pdf content"


@pytest.fixture
def mock_agent():
    """Mock agent for API tests."""
    agent = Mock()
    agent.invoke = AsyncMock()
    return agent
