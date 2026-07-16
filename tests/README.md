# Test Suite for Financial-Report Insight Agent

This directory contains integration and end-to-end tests for the financial-report insight agent.

## Directory Structure

```
tests/
├── conftest.py                          # Shared fixtures
├── integration/
│   ├── test_figure_extraction.py        # UC-01, UC-08: Figure extraction & grounding
│   ├── test_citation_system.py          # UC-07: Citation system
│   ├── test_computation_module.py       # UC-02, UC-06, UC-08: Safe computation
│   ├── test_anomaly_detection.py        # UC-03, UC-09: Anomaly detection
│   ├── test_guardrail.py                # UC-04, UC-10: Guardrail system
│   ├── test_trade_tool.py              # UC-05: Trade tool
│   ├── test_api_endpoints.py           # REST API endpoints
│   └── test_websocket.py              # WebSocket streaming
└── e2e/
    └── test_full_pipeline.py           # Full pipeline E2E tests
```

## Running Tests

### Run All Tests

```bash
pytest tests/ -v
```

### Run Integration Tests Only

```bash
pytest tests/integration/ -v
```

### Run E2E Tests Only

```bash
pytest tests/e2e/ -v
```

### Run Specific Test Class

```bash
pytest tests/integration/test_guardrail.py::TestNoAdviceEnforcement -v
```

### Run Tests with Coverage

```bash
pytest tests/ --cov=backend --cov-report=html
```

### Run Tests in Parallel

```bash
pytest tests/ -n auto
```

## Test Coverage

| Test File | Covers | Use Cases |
|-----------|--------|-----------|
| test_figure_extraction.py | F-GND-01 to F-GND-04 | UC-01, UC-08 |
| test_citation_system.py | F-CIT-01 to F-CIT-04 | UC-07 |
| test_computation_module.py | F-CMP-01 to F-CMP-06 | UC-02, UC-06, UC-08 |
| test_anomaly_detection.py | F-ANM-01 to F-ANM-05 | UC-03, UC-09 |
| test_guardrail.py | F-GRD-01 to F-GRD-04 | UC-04, UC-10 |
| test_trade_tool.py | F-TRD-01 to F-TRD-06 | UC-05 |
| test_api_endpoints.py | API layer | All |
| test_websocket.py | WebSocket streaming | All |
| test_full_pipeline.py | Full pipeline | UC-01 to UC-10 |

## Test Data

Test fixtures are defined in `conftest.py`:

- `sample_10k_content`: Minimal 10-K style document content
- `sample_figures`: Pre-extracted figures with source locations
- `sample_computations`: Pre-computed financial metrics
- `sample_anomalies`: Pre-detected anomalies with severity
- `sample_state`: Full agent state for testing

## Writing New Tests

1. Use existing fixtures from `conftest.py`
2. Follow the naming convention `test_<feature>.py`
3. Add docstrings explaining what the test covers
4. Use `@pytest.mark.asyncio` for async tests
5. Mock external dependencies (LLM, database)

## CI Integration

Tests run automatically in GitHub Actions:

```yaml
- name: Run tests
  run: pytest tests/ -v --cov=backend

- name: Upload coverage
  uses: codecov/codecov-action@v3
```
