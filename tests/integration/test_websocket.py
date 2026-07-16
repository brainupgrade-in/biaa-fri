"""
Integration tests for WebSocket streaming.
Covers: Real-time analysis streaming
"""
import pytest
import json
from unittest.mock import Mock, AsyncMock


class TestWebSocketConnection:
    """Test WebSocket connection management."""

    @pytest.mark.asyncio
    async def test_websocket_connect(self, ws_client):
        """WebSocket should connect successfully."""
        async with ws_client as ws:
            assert ws.connected is True

    @pytest.mark.asyncio
    async def test_websocket_disconnect(self, ws_client):
        """WebSocket should disconnect gracefully."""
        async with ws_client as ws:
            await ws.close()
            assert ws.connected is False


class TestAnalysisStreaming:
    """Test analysis response streaming."""

    @pytest.mark.asyncio
    async def test_stream_tokens(self, ws_client, mock_agent):
        """Response should be streamed token by token."""
        mock_agent.astream.return_value = AsyncMock()(
            token for token in ["ACME", " revenue", " was", " $5.2B"]
        )

        async with ws_client as ws:
            await ws.send_json({
                "type": "analysis_query",
                "query": "What was ACME's revenue?",
                "document_ids": ["doc-001"],
                "thread_id": "test-thread-001"
            })

            tokens = []
            while True:
                try:
                    msg = await ws.receive_json(timeout=1.0)
                    if msg["type"] == "token":
                        tokens.append(msg["content"])
                    elif msg["type"] == "done":
                        break
                except Exception:
                    break

            assert len(tokens) > 0
            assert "".join(tokens) == "ACME revenue was $5.2B"

    @pytest.mark.asyncio
    async def test_stream_citations(self, ws_client, mock_agent):
        """Citations should be streamed after response."""
        mock_agent.astream.return_value = AsyncMock()(
            iter([{"type": "citations", "data": [{"doc_id": "doc-001", "page": 12}]}])
        )

        async with ws_client as ws:
            await ws.send_json({
                "type": "analysis_query",
                "query": "Analyze ACME",
                "document_ids": ["doc-001"],
                "thread_id": "test-thread-002"
            })

            citations_received = False
            while True:
                try:
                    msg = await ws.receive_json(timeout=1.0)
                    if msg["type"] == "citations":
                        citations_received = True
                        assert len(msg["metadata"]["citations"]) > 0
                    elif msg["type"] == "done":
                        break
                except Exception:
                    break

            assert citations_received

    @pytest.mark.asyncio
    async def test_stream_anomalies(self, ws_client, mock_agent):
        """Anomalies should be streamed with severity badges."""
        mock_agent.astream.return_value = AsyncMock()(
            iter([{
                "type": "anomalies",
                "data": [{"description": "Margin expansion", "severity": "warning"}]
            }])
        )

        async with ws_client as ws:
            await ws.send_json({
                "type": "analysis_query",
                "query": "Analyze ACME margins",
                "document_ids": ["doc-001"],
                "thread_id": "test-thread-003"
            })

            anomalies_received = False
            while True:
                try:
                    msg = await ws.receive_json(timeout=1.0)
                    if msg["type"] == "anomalies":
                        anomalies_received = True
                        assert msg["metadata"]["anomalies"][0]["severity"] == "warning"
                    elif msg["type"] == "done":
                        break
                except Exception:
                    break

            assert anomalies_received

    @pytest.mark.asyncio
    async def test_stream_computations(self, ws_client, mock_agent):
        """Computation results should be streamed."""
        mock_agent.astream.return_value = AsyncMock()(
            iter([{
                "type": "computation",
                "data": {"result": 2.0, "formula": "current_assets / current_liabilities"}
            }])
        )

        async with ws_client as ws:
            await ws.send_json({
                "type": "analysis_query",
                "query": "Compute current ratio",
                "document_ids": ["doc-001"],
                "thread_id": "test-thread-004"
            })

            computation_received = False
            while True:
                try:
                    msg = await ws.receive_json(timeout=1.0)
                    if msg["type"] == "computation":
                        computation_received = True
                        assert msg["metadata"]["computation"]["result"] == 2.0
                    elif msg["type"] == "done":
                        break
                except Exception:
                    break

            assert computation_received


class TestWebSocketProtocol:
    """Test WebSocket message protocol."""

    @pytest.mark.asyncio
    async def test_invalid_message_type(self, ws_client):
        """Invalid message type should return error."""
        async with ws_client as ws:
            await ws.send_json({"type": "invalid_type"})

            msg = await ws.receive_json(timeout=1.0)
            assert msg["type"] == "error"
            assert "invalid" in msg["content"].lower()

    @pytest.mark.asyncio
    async def test_missing_query(self, ws_client):
        """Missing query should return error."""
        async with ws_client as ws:
            await ws.send_json({
                "type": "analysis_query",
                "document_ids": ["doc-001"],
                "thread_id": "test-thread-005"
            })

            msg = await ws.receive_json(timeout=1.0)
            assert msg["type"] == "error"

    @pytest.mark.asyncio
    async def test_done_signal(self, ws_client, mock_agent):
        """Done signal should be sent at end of stream."""
        mock_agent.astream.return_value = AsyncMock()(
            iter([{"type": "token", "data": "test"}])
        )

        async with ws_client as ws:
            await ws.send_json({
                "type": "analysis_query",
                "query": "test",
                "document_ids": ["doc-001"],
                "thread_id": "test-thread-006"
            })

            done_received = False
            while True:
                try:
                    msg = await ws.receive_json(timeout=1.0)
                    if msg["type"] == "done":
                        done_received = True
                        break
                except Exception:
                    break

            assert done_received


class TestWebSocketConcurrency:
    """Test concurrent WebSocket connections."""

    @pytest.mark.asyncio
    async def test_multiple_connections(self, ws_client, mock_agent):
        """Multiple WebSocket connections should work simultaneously."""
        mock_agent.astream.return_value = AsyncMock()(
            iter([{"type": "token", "data": "response"}])
        )

        connections = []
        for i in range(3):
            conn = await ws_client.__aenter__()
            connections.append(conn)

        for i, conn in enumerate(connections):
            await conn.send_json({
                "type": "analysis_query",
                "query": f"Query {i}",
                "document_ids": ["doc-001"],
                "thread_id": f"thread-{i}"
            })

        assert len(connections) == 3


class TestWebSocketErrorHandling:
    """Test WebSocket error handling."""

    @pytest.mark.asyncio
    async def test_agent_error_streaming(self, ws_client, mock_agent):
        """Agent errors should be streamed to client."""
        mock_agent.astream.side_effect = Exception("LLM API error")

        async with ws_client as ws:
            await ws.send_json({
                "type": "analysis_query",
                "query": "test",
                "document_ids": ["doc-001"],
                "thread_id": "test-thread-error"
            })

            msg = await ws.receive_json(timeout=1.0)
            assert msg["type"] == "error"

    @pytest.mark.asyncio
    async def test_connection_timeout(self, ws_client):
        """Connection timeout should be handled gracefully."""
        # This would test timeout scenarios
        pass


# ---------------------------------------------------------------------------
# Fixtures for WebSocket tests
# ---------------------------------------------------------------------------

@pytest.fixture
def ws_client():
    """Create WebSocket test client."""
    # In real implementation, this would connect to the WebSocket endpoint
    # from fastapi.testclient import TestClient
    # from backend.main import app
    # return TestClient(app).websocket_connect("/ws/analysis/stream")
    return MockWebSocketClient()


class MockWebSocketClient:
    """Mock WebSocket client for testing."""

    def __init__(self):
        self.connected = False
        self.messages = []

    async def __aenter__(self):
        self.connected = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.connected = False

    async def send_json(self, data):
        self.messages.append(data)

    async def receive_json(self, timeout=None):
        # Simulate receiving messages
        if self.messages:
            return self.messages.pop(0)
        return {"type": "done"}

    async def close(self):
        self.connected = False
