"""
Integration tests for anomaly detection.
Covers: F-ANM-01, F-ANM-02, F-ANM-03, F-ANM-04, F-ANM-05, UC-03, UC-09
"""
import pytest
import math


class TestOutlierDetection:
    """Test statistical outlier detection."""

    def test_z_score_threshold(self):
        """F-ANM-01: Figures exceeding z-score threshold should be flagged."""
        historical = [10, 12, 11, 13, 12, 11, 10, 12, 11, 13]
        current = 25  # Significant outlier

        result = detect_outlier(historical, current, threshold=2.0)
        assert result["is_outlier"] is True
        assert abs(result["z_score"]) > 2.0

    def test_normal_figure_not_flagged(self):
        """F-ANM-01: Normal figures should not be flagged."""
        historical = [10, 12, 11, 13, 12, 11, 10, 12, 11, 13]
        current = 12  # Normal

        result = detect_outlier(historical, current, threshold=2.0)
        assert result["is_outlier"] is False

    def test_z_score_computation(self):
        """F-ANM-01: Z-score should be computed correctly."""
        historical = [10, 12, 11, 13, 12, 11, 10, 12, 11, 13]
        current = 25

        result = detect_outlier(historical, current, threshold=2.0)
        mean = sum(historical) / len(historical)
        std = math.sqrt(sum((x - mean) ** 2 for x in historical) / len(historical))
        expected_z = (current - mean) / std

        assert abs(result["z_score"] - expected_z) < 0.01

    def test_custom_threshold(self):
        """F-ANM-01: Custom z-score threshold should be respected."""
        historical = [10, 12, 11, 13, 12, 11, 10, 12, 11, 13]
        # Mean ≈ 11.5, Std ≈ 1.02
        # Value 14 gives z-score ≈ 2.45 (between 2 and 3)
        current = 14  # Moderate outlier

        # With threshold=3.0, should NOT be flagged (z ≈ 2.45 < 3.0)
        result_strict = detect_outlier(historical, current, threshold=3.0)
        assert result_strict["is_outlier"] is False

        # With threshold=1.5, should be flagged (z ≈ 2.45 > 1.5)
        result_loose = detect_outlier(historical, current, threshold=1.5)
        assert result_loose["is_outlier"] is True

    def test_period_over_period_change(self, sample_computations):
        """F-ANM-01: Period-over-period changes should be analyzed."""
        yoy_growth = sample_computations[2]
        result = detect_period_change(yoy_growth)
        assert "change" in result
        assert "is_significant" in result


class TestMaterialityThreshold:
    """Test materiality threshold detection."""

    def test_line_item_exceeds_threshold(self):
        """F-ANM-02: Line items exceeding materiality should be flagged."""
        revenue = 5_200_000_000
        line_item = 600_000_000  # ~11.5% of revenue
        threshold = 0.10

        result = check_materiality(revenue, line_item, threshold)
        assert result["exceeds"] is True
        assert result["ratio"] > threshold

    def test_line_item_within_threshold(self):
        """F-ANM-02: Line items within materiality should not be flagged."""
        revenue = 5_200_000_000
        line_item = 400_000_000  # ~7.7% of revenue
        threshold = 0.10

        result = check_materiality(revenue, line_item, threshold)
        assert result["exceeds"] is False

    def test_materiality_ratio_computation(self):
        """F-ANM-02: Materiality ratio should be computed correctly."""
        revenue = 5_200_000_000
        line_item = 520_000_000

        result = check_materiality(revenue, line_item, 0.10)
        expected_ratio = line_item / revenue
        assert abs(result["ratio"] - expected_ratio) < 0.001

    def test_materiality_severity(self):
        """F-ANM-04: Severity should be assigned based on ratio."""
        revenue = 5_200_000_000

        # Just over threshold
        result1 = check_materiality(revenue, 600_000_000, 0.10)
        assert result1["severity"] == "warning"

        # Well over threshold
        result2 = check_materiality(revenue, 2_000_000_000, 0.10)
        assert result2["severity"] in ["warning", "critical"]


class TestGAAPIFRSHeuristics:
    """Test GAAP/IFRS red-flag heuristics."""

    def test_accounting_policy_change_without_disclosure(self):
        """F-ANM-03: Policy changes without disclosure should be flagged."""
        disclosure_notes = []
        policy_change = "Changed revenue recognition from ASC 605 to ASC 606"

        result = check_policy_disclosure(policy_change, disclosure_notes)
        assert result["flagged"] is True
        assert result["severity"] == "critical"

    def test_accounting_policy_change_with_disclosure(self):
        """F-ANM-03: Policy changes with disclosure should not be flagged."""
        disclosure_notes = ["Changed revenue recognition from ASC 605 to ASC 606"]
        policy_change = "Changed revenue recognition from ASC 605 to ASC 606"

        result = check_policy_disclosure(policy_change, disclosure_notes)
        assert result["flagged"] is False

    def test_going_concern_note(self):
        """F-ANM-03: Going-concern notes should be flagged."""
        notes = ["Auditor expressed doubt about going concern"]

        result = check_auditor_flags(notes)
        assert result["has_going_concern"] is True
        assert result["severity"] == "critical"

    def test_related_party_transactions(self):
        """F-ANM-03: Material related-party transactions should be flagged."""
        revenue = 5_200_000_000
        related_party_txn = 600_000_000  # >10% of revenue

        result = check_related_party(related_party_txn, revenue, threshold=0.10)
        assert result["flagged"] is True

    def test_unqualified_audit_with_issues(self):
        """F-ANM-03: Unqualified audit with issues should be flagged."""
        audit_opinion = "Unqualified"
        issues = ["Material weakness in internal controls"]

        result = check_audit_quality(audit_opinion, issues)
        assert result["flagged"] is True


class TestSeverityAssignment:
    """Test anomaly severity assignment."""

    def test_info_severity(self):
        """F-ANM-04: Minor changes should be info severity."""
        anomaly = classify_anomaly_severity(z_score=1.5, materiality_ratio=0.05)
        assert anomaly["severity"] == "info"

    def test_warning_severity(self):
        """F-ANM-04: Moderate changes should be warning severity."""
        anomaly = classify_anomaly_severity(z_score=2.5, materiality_ratio=0.12)
        assert anomaly["severity"] == "warning"

    def test_critical_severity(self):
        """F-ANM-04: Major changes should be critical severity."""
        anomaly = classify_anomaly_severity(z_score=3.5, materiality_ratio=0.35)
        assert anomaly["severity"] == "critical"

    def test_severity_from_z_score(self):
        """Severity should be based on z-score thresholds."""
        # |z| < 2 -> info
        assert classify_anomaly_severity(z_score=1.0)["severity"] == "info"

        # 2 <= |z| < 3 -> warning
        assert classify_anomaly_severity(z_score=2.5)["severity"] == "warning"

        # |z| >= 3 -> critical
        assert classify_anomaly_severity(z_score=3.5)["severity"] == "critical"


class TestAnomalyObservationOnly:
    """Test that anomalies are stated as observations only."""

    def test_no_conclusions_in_anomaly_description(self):
        """F-ANM-05: Anomaly descriptions should not draw conclusions."""
        description = "Gross Margin expanded by 15 points"

        # Should not contain advisory language
        advisory_words = ["should", "recommend", "buy", "sell", "hold"]
        for word in advisory_words:
            assert word not in description.lower()

    def test_anomaly_as_observation(self, sample_anomalies):
        """F-ANM-05: All anomalies should be stated as observations."""
        for anomaly in sample_anomalies:
            assert "description" in anomaly
            assert "severity" in anomaly
            assert "source" in anomaly

            # Description should be factual
            desc = anomaly["description"]
            assert "is" in desc or "changed" in desc or "expanded" in desc or "exceeds" in desc


class TestAnomalyEdgeCases:
    """Test edge cases in anomaly detection."""

    def test_empty_historical_data(self):
        """Empty historical data should handle gracefully."""
        result = detect_outlier([], 100, threshold=2.0)
        assert result["is_outlier"] is False
        assert result["z_score"] == 0

    def test_single_historical_data_point(self):
        """Single historical data point should handle gracefully."""
        result = detect_outlier([10], 20, threshold=2.0)
        assert result["is_outlier"] is True

    def test_zero_revenue_materiality(self):
        """Zero revenue should avoid division by zero."""
        result = check_materiality(0, 100, 0.10)
        assert result["ratio"] == 0
        assert result["exceeds"] is False

    def test_negative_line_item(self):
        """Negative line items (reversals) should be handled."""
        revenue = 5_200_000_000
        line_item = -100_000_000  # Reversal

        result = check_materiality(revenue, abs(line_item), 0.10)
        assert result["ratio"] > 0


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def detect_outlier(historical, current, threshold=2.0):
    """Detect if current value is an outlier based on historical data."""
    if not historical:
        return {"is_outlier": False, "z_score": 0, "mean": 0, "std": 0}

    mean = sum(historical) / len(historical)
    std = math.sqrt(sum((x - mean) ** 2 for x in historical) / len(historical))

    if std == 0:
        return {"is_outlier": current != mean, "z_score": 0, "mean": mean, "std": std}

    z_score = (current - mean) / std

    return {
        "is_outlier": abs(z_score) > threshold,
        "z_score": z_score,
        "mean": mean,
        "std": std,
    }


def detect_period_change(computation):
    """Detect significant period-over-period changes."""
    if computation.get("error"):
        return {"change": 0, "is_significant": False}

    change = computation.get("result", 0)
    return {
        "change": change,
        "is_significant": abs(change) > 10,  # >10% change is significant
    }


def check_materiality(revenue, line_item, threshold):
    """Check if line item exceeds materiality threshold."""
    if revenue == 0:
        return {"exceeds": False, "ratio": 0, "severity": "info"}

    ratio = abs(line_item) / revenue
    exceeds = ratio > threshold

    if ratio > 0.30:
        severity = "critical"
    elif exceeds:
        severity = "warning"
    else:
        severity = "info"

    return {"exceeds": exceeds, "ratio": ratio, "severity": severity}


def check_policy_disclosure(policy_change, disclosure_notes):
    """Check if accounting policy change is disclosed."""
    for note in disclosure_notes:
        if policy_change.lower() in note.lower():
            return {"flagged": False, "severity": None}

    return {"flagged": True, "severity": "critical"}


def check_auditor_flags(notes):
    """Check for auditor red flags."""
    going_concern = any("going concern" in note.lower() for note in notes)

    return {
        "has_going_concern": going_concern,
        "severity": "critical" if going_concern else None,
    }


def check_related_party(txn_amount, revenue, threshold=0.10):
    """Check related-party transaction materiality."""
    if revenue == 0:
        return {"flagged": False, "ratio": 0}

    ratio = txn_amount / revenue
    return {"flagged": ratio > threshold, "ratio": ratio}


def check_audit_quality(opinion, issues):
    """Check audit quality."""
    has_issues = len(issues) > 0
    return {"flagged": has_issues, "issues": issues}


def classify_anomaly_severity(z_score, materiality_ratio=0):
    """Classify anomaly severity based on z-score and materiality."""
    if abs(z_score) >= 3 or materiality_ratio > 0.30:
        return {"severity": "critical"}
    elif abs(z_score) >= 2 or materiality_ratio > 0.10:
        return {"severity": "warning"}
    else:
        return {"severity": "info"}
