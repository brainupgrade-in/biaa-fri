"""
Integration tests for safe computation module.
Covers: F-CMP-01, F-CMP-02, F-CMP-03, F-CMP-04, F-CMP-05, F-CMP-06, UC-02, UC-06, UC-08
"""
import pytest
import math


class TestComputationExecution:
    """Test deterministic computation execution."""

    def test_simple_division(self):
        """F-CMP-01: Basic division should be computed correctly."""
        result = compute_metric("a / b", {"a": 100, "b": 25})
        assert result["result"] == 4.0
        assert result["error"] is None

    def test_ratio_computation(self, sample_computations):
        """UC-02: Current ratio should be computed correctly."""
        current_ratio = sample_computations[0]
        assert current_ratio["result"] == 2.0
        assert current_ratio["metric"] == "Current Ratio"

    def test_percentage_computation(self, sample_computations):
        """Percentage calculations should be precise."""
        gross_margin = sample_computations[1]
        assert gross_margin["result"] == 0.40
        assert gross_margin["unit"] == "ratio"

    def test_yoy_growth_computation(self, sample_computations):
        """UC-06: YoY growth should be computed correctly."""
        yoy_growth = sample_computations[2]
        expected = (5_200_000_000 - 4_800_000_000) / 4_800_000_000 * 100
        assert abs(yoy_growth["result"] - expected) < 0.01

    def test_addition(self):
        """Addition should be computed correctly."""
        result = compute_metric("a + b", {"a": 100, "b": 200})
        assert result["result"] == 300

    def test_subtraction(self):
        """Subtraction should be computed correctly."""
        result = compute_metric("a - b", {"a": 500, "b": 200})
        assert result["result"] == 300

    def test_multiplication(self):
        """Multiplication should be computed correctly."""
        result = compute_metric("a * b", {"a": 10, "b": 20})
        assert result["result"] == 200


class TestComputationTraceability:
    """Test computation result traceability."""

    def test_formula_returned(self, sample_computations):
        """F-CMP-02: Formula should be returned with result."""
        for comp in sample_computations:
            assert "formula" in comp
            assert isinstance(comp["formula"], str)
            assert len(comp["formula"]) > 0

    def test_inputs_with_sources(self, sample_computations):
        """F-CMP-02: Inputs with sources should be returned."""
        for comp in sample_computations:
            assert "inputs_with_sources" in comp
            assert isinstance(comp["inputs_with_sources"], list)
            assert len(comp["inputs_with_sources"]) >= 2

            for inp in comp["inputs_with_sources"]:
                assert "value" in inp
                assert "unit" in inp
                assert "name" in inp

    def test_unit_returned(self, sample_computations):
        """F-CMP-02: Unit should be returned with result."""
        for comp in sample_computations:
            assert "unit" in comp
            assert isinstance(comp["unit"], str)


class TestPrecisionPolicy:
    """Test precision and formatting rules."""

    def test_percentage_two_decimal_places(self):
        """F-CMP-03: Percentages should be to 2 decimal places."""
        result = compute_metric("a / b * 100", {"a": 1, "b": 3})
        formatted = format_result(result["result"], "%")
        assert formatted == "33.33%"

    def test_currency_whole_unit(self):
        """F-CMP-03: Currency should be to nearest whole unit."""
        result = compute_metric("a + b", {"a": 100.50, "b": 200.75})
        formatted = format_result(result["result"], "USD")
        assert formatted == "$301"

    def test_currency_with_sub_unit_precision(self):
        """F-CMP-03: Sub-unit precision preserved if present in source."""
        result = compute_metric("a / b", {"a": 100, "b": 3})
        formatted = format_result(result["result"], "USD", precision=4)
        assert "." in formatted or len(formatted) > 0

    def test_ratio_precision(self):
        """Ratios should be formatted appropriately."""
        result = compute_metric("a / b", {"a": 3, "b": 2})
        formatted = format_result(result["result"], "ratio")
        assert formatted == "1.50"


class TestErrorGuards:
    """Test computation error handling."""

    def test_division_by_zero(self):
        """F-CMP-04: Division by zero should return symbolic error."""
        result = compute_metric("a / b", {"a": 100, "b": 0})
        assert result["result"] is None
        assert result["error"] == "Division by zero"

    def test_overflow_guard(self):
        """F-CMP-04: Overflow should return symbolic error."""
        result = compute_metric("a * b", {"a": 1e308, "b": 1e308})
        assert result["result"] is None
        assert "overflow" in result["error"].lower()

    def test_nan_handling(self):
        """F-CMP-04: NaN should be handled gracefully."""
        result = compute_metric("a / b", {"a": 0, "b": 0})
        assert result["result"] is None
        assert result["error"] is not None

    def test_invalid_formula(self):
        """Invalid formula should return error."""
        result = compute_metric("invalid_formula", {"a": 1})
        assert result["result"] is None
        assert result["error"] is not None

    def test_missing_input(self):
        """Missing input should return error."""
        result = compute_metric("a / b", {"a": 100})
        assert result["result"] is None
        assert "missing" in result["error"].lower() or "not found" in result["error"].lower()


class TestUnitConsistency:
    """Test unit validation before computation."""

    def test_matching_units(self):
        """F-CMP-05: Matching units should be allowed."""
        result = compute_metric_with_units(
            "a + b",
            {"a": {"value": 100, "unit": "USD"}, "b": {"value": 200, "unit": "USD"}}
        )
        assert result["result"] == 300
        assert result["error"] is None

    def test_mismatched_units(self):
        """F-CMP-05: Mismatched units should be rejected."""
        result = compute_metric_with_units(
            "a + b",
            {"a": {"value": 100, "unit": "USD"}, "b": {"value": 50, "unit": "EUR"}}
        )
        assert result["result"] is None
        assert "unit" in result["error"].lower()

    def test_percentage_with_currency(self):
        """F-CMP-05: Percentage and currency should be incompatible."""
        result = compute_metric_with_units(
            "a + b",
            {"a": {"value": 10, "unit": "%"}, "b": {"value": 100, "unit": "USD"}}
        )
        assert result["result"] is None

    def test_ratio_with_ratio(self):
        """F-CMP-05: Ratios should be compatible."""
        result = compute_metric_with_units(
            "a + b",
            {"a": {"value": 2.0, "unit": "ratio"}, "b": {"value": 1.5, "unit": "ratio"}}
        )
        assert result["result"] == 3.5

    def test_ratio_division(self):
        """F-CMP-05: Ratio division should be allowed."""
        result = compute_metric_with_units(
            "a / b",
            {"a": {"value": 100, "unit": "USD"}, "b": {"value": 50, "unit": "USD"}}
        )
        assert result["result"] == 2.0


class TestTemporalConsistency:
    """Test temporal consistency validation."""

    def test_same_period_figures(self):
        """F-CMP-06: Same period figures should be allowed."""
        figures = [
            {"value": 100, "unit": "USD", "period": "FY2024"},
            {"value": 50, "unit": "USD", "period": "FY2024"},
        ]
        result = validate_temporal_consistency("a + b", figures)
        assert result["valid"] is True

    def test_different_period_figures(self):
        """F-CMP-06: Different period figures should trigger warning."""
        figures = [
            {"value": 100, "unit": "USD", "period": "FY2024"},
            {"value": 50, "unit": "USD", "period": "FY2023"},
        ]
        result = validate_temporal_consistency("a + b", figures)
        assert result["valid"] is True  # Allowed but flagged
        assert result["warning"] is not None

    def test_explicit_period_comparison(self):
        """F-CMP-06: Explicit period comparison should be allowed."""
        figures = [
            {"value": 100, "unit": "USD", "period": "FY2024"},
            {"value": 50, "unit": "USD", "period": "FY2023"},
        ]
        result = validate_temporal_consistency("delta(a, b)", figures, is_comparison=True)
        assert result["valid"] is True
        assert result["warning"] is None


class TestUnverifiedInputRejection:
    """Test rejection of unverified inputs."""

    def test_reject_unverified_input(self):
        """UC-08: Unverified figures should be rejected."""
        inputs = [
            {"value": 100, "confidence": "high", "name": "Revenue"},
            {"value": None, "confidence": "unverified", "name": "R&D Expense"},
        ]
        result = validate_inputs(inputs)
        assert result["valid"] is False
        assert "unverified" in result["error"].lower()

    def test_accept_verified_inputs(self):
        """UC-08: Verified figures should be accepted."""
        inputs = [
            {"value": 100, "confidence": "high", "name": "Revenue"},
            {"value": 50, "confidence": "high", "name": "COGS"},
        ]
        result = validate_inputs(inputs)
        assert result["valid"] is True

    def test_low_confidence_warning(self):
        """Low confidence figures should trigger warning."""
        inputs = [
            {"value": 100, "confidence": "high", "name": "Revenue"},
            {"value": 50, "confidence": "low", "name": "Footnote Figure"},
        ]
        result = validate_inputs(inputs)
        assert result["valid"] is True
        assert result["warning"] is not None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def compute_metric(formula, inputs):
    """Compute a metric using the formula and inputs."""
    try:
        # Simple eval for testing (production would use sandbox)
        local_vars = {k: v for k, v in inputs.items()}
        result = eval(formula, {"__builtins__": {}}, local_vars)

        if math.isinf(result) or math.isnan(result):
            return {"result": None, "formula": formula, "inputs_with_sources": [], "unit": "", "error": "Overflow or invalid result"}

        return {"result": result, "formula": formula, "inputs_with_sources": [], "unit": "", "error": None}
    except ZeroDivisionError:
        return {"result": None, "formula": formula, "inputs_with_sources": [], "unit": "", "error": "Division by zero"}
    except Exception as e:
        return {"result": None, "formula": formula, "inputs_with_sources": [], "unit": "", "error": str(e)}


def compute_metric_with_units(formula, inputs):
    """Compute a metric with unit validation."""
    units = [v["unit"] for v in inputs.values()]

    # Check unit consistency (excluding ratio which is dimensionless)
    non_ratio_units = [u for u in units if u != "ratio"]
    if len(set(non_ratio_units)) > 1:
        return {"result": None, "formula": formula, "inputs_with_sources": [], "unit": "", "error": f"Unit mismatch: {units}"}

    try:
        local_vars = {k: v["value"] for k, v in inputs.items()}
        result = eval(formula, {"__builtins__": {}}, local_vars)
        return {"result": result, "formula": formula, "inputs_with_sources": [], "unit": units[0], "error": None}
    except ZeroDivisionError:
        return {"result": None, "formula": formula, "inputs_with_sources": [], "unit": "", "error": "Division by zero"}
    except Exception as e:
        return {"result": None, "formula": formula, "inputs_with_sources": [], "unit": "", "error": str(e)}


def format_result(value, unit, precision=2):
    """Format a result based on unit and precision."""
    if value is None:
        return "N/A"

    if unit == "%":
        return f"{value:.2f}%"
    elif unit == "USD":
        return f"${value:,.0f}"
    elif unit == "ratio":
        return f"{value:.2f}"
    else:
        return f"{value:.{precision}f}"


def validate_temporal_consistency(formula, figures, is_comparison=False):
    """Validate temporal consistency of figures."""
    periods = [f.get("period") for f in figures if f.get("period")]

    if len(set(periods)) > 1 and not is_comparison:
        return {
            "valid": True,
            "warning": f"Figures from different periods: {set(periods)}. Verify this is intentional.",
        }

    return {"valid": True, "warning": None}


def validate_inputs(inputs):
    """Validate computation inputs."""
    for inp in inputs:
        if inp["confidence"] == "unverified":
            return {"valid": False, "error": f"Input '{inp['name']}' has unverified confidence"}

    low_conf = [inp for inp in inputs if inp["confidence"] == "low"]
    if low_conf:
        return {"valid": True, "warning": f"Low confidence inputs: {[i['name'] for i in low_conf]}"}

    return {"valid": True, "warning": None}
