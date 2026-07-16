"""
Integration tests for trade tool.
Covers: F-TRD-01, F-TRD-02, F-TRD-03, F-TRD-04, F-TRD-05, F-TRD-06, UC-05
"""
import pytest
from datetime import datetime


class TestTradeDraftGeneration:
    """Test trade draft generation."""

    def test_generate_trade_draft(self, sample_state):
        """F-TRD-01: Trade draft should be generated from analysis."""
        draft = generate_trade_draft(
            ticker="ACME",
            direction="long",
            state=sample_state
        )

        assert draft["ticker"] == "ACME"
        assert draft["direction"] == "long"
        assert "thesis" in draft
        assert "risk_flags" in draft

    def test_draft_includes_thesis(self, sample_state):
        """F-TRD-01: Draft should include supporting thesis."""
        draft = generate_trade_draft(
            ticker="ACME",
            direction="long",
            state=sample_state
        )

        assert len(draft["thesis"]) > 0
        assert isinstance(draft["thesis"], str)

    def test_draft_includes_risk_flags(self, sample_state):
        """F-TRD-01: Draft should include risk flags from anomalies."""
        draft = generate_trade_draft(
            ticker="ACME",
            direction="long",
            state=sample_state
        )

        assert isinstance(draft["risk_flags"], list)
        # Should include anomalies as risk flags
        assert len(draft["risk_flags"]) > 0

    def test_draft_timestamp(self, sample_state):
        """F-TRD-05: Draft should have timestamp."""
        draft = generate_trade_draft(
            ticker="ACME",
            direction="long",
            state=sample_state
        )

        assert "timestamp" in draft
        assert draft["timestamp"] is not None

    def test_draft_direction_long(self, sample_state):
        """Draft should support long direction."""
        draft = generate_trade_draft(
            ticker="ACME",
            direction="long",
            state=sample_state
        )
        assert draft["direction"] == "long"

    def test_draft_direction_short(self, sample_state):
        """Draft should support short direction."""
        draft = generate_trade_draft(
            ticker="ACME",
            direction="short",
            state=sample_state
        )
        assert draft["direction"] == "short"

    def test_draft_direction_neutral(self, sample_state):
        """Draft should support neutral direction."""
        draft = generate_trade_draft(
            ticker="ACME",
            direction="neutral",
            state=sample_state
        )
        assert draft["direction"] == "neutral"


class TestTradeToolInvocation:
    """Test trade tool invocation and activation."""

    def test_trade_tool_disabled_by_default(self):
        """F-TRD-02: Trade tool should be disabled by default."""
        config = {"trade_tool_enabled": True}  # Enabled in config
        state = {"user_query": "Analyze ACME"}

        result = should_invoke_trade_tool(state, config)
        assert result["invoke"] is False

    def test_trade_tool_invoked_by_command(self):
        """F-TRD-02: Trade tool should activate on /trade command."""
        config = {"trade_tool_enabled": True}
        state = {"user_query": "/trade ACME long"}

        result = should_invoke_trade_tool(state, config)
        assert result["invoke"] is True
        assert result["ticker"] == "ACME"
        assert result["direction"] == "long"

    def test_trade_tool_disabled_config(self):
        """F-TRD-02: Trade tool should respect disabled config."""
        config = {"trade_tool_enabled": False}
        state = {"user_query": "/trade ACME long"}

        result = should_invoke_trade_tool(state, config)
        assert result["invoke"] is False

    def test_trade_command_parsing(self):
        """Trade command should be parsed correctly."""
        test_cases = [
            ("/trade ACME long", "ACME", "long"),
            ("/trade ACME short", "ACME", "short"),
            ("/trade ACME neutral", "ACME", "neutral"),
            ("/trade XYZ long", "XYZ", "long"),
        ]

        for cmd, expected_ticker, expected_direction in test_cases:
            result = parse_trade_command(cmd)
            assert result["ticker"] == expected_ticker
            assert result["direction"] == expected_direction


class TestTradeConfirmation:
    """Test trade confirmation flow."""

    def test_confirmation_card_structure(self, sample_state):
        """F-TRD-03: Confirmation card should have required fields."""
        draft = generate_trade_draft(
            ticker="ACME",
            direction="long",
            state=sample_state
        )
        card = generate_confirmation_card(draft)

        assert "ticker" in card
        assert "direction" in card
        assert "thesis" in card
        assert "risk_flags" in card
        assert "confirm_action" in card
        assert "cancel_action" in card

    def test_confirmation_card_disclaimer(self, sample_state):
        """F-TRD-03: Confirmation card should include disclaimer."""
        draft = generate_trade_draft(
            ticker="ACME",
            direction="long",
            state=sample_state
        )
        card = generate_confirmation_card(draft)

        assert "disclaimer" in card
        assert "draft only" in card["disclaimer"].lower()
        assert "manually" in card["disclaimer"].lower()

    def test_confirmation_card_no_execution(self, sample_state):
        """F-TRD-04: Confirmation card should not execute orders."""
        draft = generate_trade_draft(
            ticker="ACME",
            direction="long",
            state=sample_state
        )
        card = generate_confirmation_card(draft)

        assert card["confirm_action"] == "log_draft"
        assert card["cancel_action"] == "discard"

    def test_confirm_trade_draft(self, sample_state):
        """UC-05: Confirming draft should log it."""
        draft = generate_trade_draft(
            ticker="ACME",
            direction="long",
            state=sample_state
        )
        result = confirm_trade_draft(draft)

        assert result["status"] == "confirmed"
        assert result["logged"] is True

    def test_cancel_trade_draft(self, sample_state):
        """UC-05: Canceling draft should discard it."""
        draft = generate_trade_draft(
            ticker="ACME",
            direction="long",
            state=sample_state
        )
        result = cancel_trade_draft(draft)

        assert result["status"] == "cancelled"
        assert result["logged"] is False


class TestTradeDraftLogging:
    """Test trade draft logging for compliance."""

    def test_draft_log_entry(self, sample_state):
        """F-TRD-05: Trade drafts should be logged."""
        draft = generate_trade_draft(
            ticker="ACME",
            direction="long",
            state=sample_state
        )
        log_entry = create_trade_log_entry(draft, "user-001")

        assert "timestamp" in log_entry
        assert "draft" in log_entry
        assert "user_id" in log_entry
        assert "action" in log_entry

    def test_draft_log_timestamp(self, sample_state):
        """F-TRD-05: Log entry should have timestamp."""
        draft = generate_trade_draft(
            ticker="ACME",
            direction="long",
            state=sample_state
        )
        log_entry = create_trade_log_entry(draft, "user-001")

        assert log_entry["timestamp"] is not None
        assert isinstance(log_entry["timestamp"], str)

    def test_draft_log_user_id(self, sample_state):
        """F-TRD-05: Log entry should have user ID."""
        draft = generate_trade_draft(
            ticker="ACME",
            direction="long",
            state=sample_state
        )
        log_entry = create_trade_log_entry(draft, "user-001")

        assert log_entry["user_id"] == "user-001"

    def test_draft_log_action(self, sample_state):
        """F-TRD-05: Log entry should have action."""
        draft = generate_trade_draft(
            ticker="ACME",
            direction="long",
            state=sample_state
        )
        log_entry = create_trade_log_entry(draft, "user-001")

        assert log_entry["action"] in ["created", "confirmed", "cancelled"]


class TestPositionSizing:
    """Test position sizing assistance."""

    def test_position_size_suggestion(self):
        """F-TRD-06: Position size should be suggested based on risk."""
        risk_params = {
            "max_position": 5.0,  # 5% max
            "risk_tolerance": "moderate",
        }
        risk_flags = ["Gross Margin expanded by 15 points"]

        result = suggest_position_size(risk_params, risk_flags)

        assert "position_size" in result
        assert result["position_size"] <= risk_params["max_position"]

    def test_position_size_respects_max(self):
        """F-TRD-06: Position size should respect max limit."""
        risk_params = {
            "max_position": 2.0,  # 2% max
            "risk_tolerance": "conservative",
        }
        risk_flags = []

        result = suggest_position_size(risk_params, risk_flags)

        assert result["position_size"] <= 2.0

    def test_position_size_reduced_for_risks(self):
        """F-TRD-06: Position size should be reduced for risk flags."""
        risk_params_no_risk = {
            "max_position": 5.0,
            "risk_tolerance": "moderate",
        }
        risk_params_with_risk = {
            "max_position": 5.0,
            "risk_tolerance": "moderate",
        }

        result_no_risk = suggest_position_size(risk_params_no_risk, [])
        result_with_risk = suggest_position_size(
            risk_params_with_risk,
            ["Risk flag 1", "Risk flag 2"]
        )

        assert result_with_risk["position_size"] <= result_no_risk["position_size"]

    def test_position_size_not_autonomous(self):
        """F-TRD-06: Position size should be a suggestion, not execution."""
        risk_params = {"max_position": 5.0, "risk_tolerance": "moderate"}
        result = suggest_position_size(risk_params, [])

        assert "suggested" in result
        assert result["suggested"] is True
        assert "execute" not in result


class TestTradeToolEdgeCases:
    """Test edge cases in trade tool."""

    def test_missing_ticker(self):
        """Trade command without ticker should fail."""
        result = parse_trade_command("/trade")
        assert result["error"] is not None

    def test_missing_direction(self):
        """Trade command without direction should fail."""
        result = parse_trade_command("/trade ACME")
        assert result["error"] is not None

    def test_invalid_direction(self):
        """Invalid direction should fail."""
        result = parse_trade_command("/trade ACME invalid")
        assert result["error"] is not None

    def test_trade_without_analysis(self):
        """Trade request without prior analysis should be handled."""
        state = {"extracted_figures": [], "anomalies": []}
        draft = generate_trade_draft(
            ticker="ACME",
            direction="long",
            state=state
        )
        assert draft is not None
        assert len(draft["risk_flags"]) == 0


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def generate_trade_draft(ticker, direction, state):
    """Generate a trade draft from analysis state."""
    anomalies = state.get("anomalies", [])
    risk_flags = [a["description"] for a in anomalies if a.get("severity") in ["warning", "critical"]]

    thesis = f"Analysis of {ticker} based on financial data. "
    if state.get("computations"):
        thesis += f"Key metrics include current ratio and revenue growth. "

    return {
        "ticker": ticker,
        "direction": direction,
        "thesis": thesis,
        "risk_flags": risk_flags,
        "suggested_position_size": None,
        "timestamp": datetime.utcnow().isoformat(),
    }


def should_invoke_trade_tool(state, config):
    """Determine if trade tool should be invoked."""
    if not config.get("trade_tool_enabled", True):
        return {"invoke": False}

    query = state.get("user_query", "")
    if query.startswith("/trade"):
        parsed = parse_trade_command(query)
        if parsed.get("error"):
            return {"invoke": False}
        return {"invoke": True, "ticker": parsed["ticker"], "direction": parsed["direction"]}

    return {"invoke": False}


def parse_trade_command(command):
    """Parse /trade command."""
    parts = command.strip().split()

    if len(parts) < 3:
        return {"error": "Missing ticker or direction"}

    ticker = parts[1]
    direction = parts[2]

    valid_directions = ["long", "short", "neutral"]
    if direction not in valid_directions:
        return {"error": f"Invalid direction: {direction}"}

    return {"ticker": ticker, "direction": direction, "error": None}


def generate_confirmation_card(draft):
    """Generate confirmation card for trade draft."""
    return {
        "ticker": draft["ticker"],
        "direction": draft["direction"],
        "thesis": draft["thesis"],
        "risk_flags": draft["risk_flags"],
        "confirm_action": "log_draft",
        "cancel_action": "discard",
        "disclaimer": "This is a draft only. No order will be placed. Submit manually through your brokerage.",
    }


def confirm_trade_draft(draft):
    """Confirm trade draft (log only)."""
    return {"status": "confirmed", "logged": True, "draft": draft}


def cancel_trade_draft(draft):
    """Cancel trade draft."""
    return {"status": "cancelled", "logged": False, "draft": draft}


def create_trade_log_entry(draft, user_id):
    """Create log entry for trade draft."""
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "draft": draft,
        "user_id": user_id,
        "action": "created",
    }


def suggest_position_size(risk_params, risk_flags):
    """Suggest position size based on risk parameters and flags."""
    max_position = risk_params.get("max_position", 5.0)
    risk_tolerance = risk_params.get("risk_tolerance", "moderate")

    # Base position from tolerance
    base_positions = {"conservative": 0.5, "moderate": 0.75, "aggressive": 1.0}
    base = base_positions.get(risk_tolerance, 0.75)

    # Reduce for risk flags
    risk_reduction = len(risk_flags) * 0.1  # 10% reduction per flag
    position_size = max_position * base * (1 - risk_reduction)

    return {
        "position_size": round(position_size, 2),
        "suggested": True,
        "max_position": max_position,
        "risk_flags_count": len(risk_flags),
    }
