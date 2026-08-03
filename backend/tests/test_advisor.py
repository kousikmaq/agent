"""Tests for the LLM planning advisor (goal -> weights, comparison -> recommend).

Uses a fake chat-completion client (no Azure access) to verify the advisor's
output is strictly validated: only known objective terms with safe integer
weights survive, malformed/hostile output falls back to safe defaults, and the
scenario recommender only ever returns a scenario type it was actually shown.
The advisor never runs the solver, so these tests need no factory data.
"""

from __future__ import annotations

from app.advisor import PlanningGoalAdvisor, ScenarioAdvisor
from app.advisor.goal_advisor import _validate_weights
from app.advisor.parsing import extract_json_object
from app.advisor.terms import ALLOWED_TERMS, WEIGHT_MAX
from app.domain.enums import ScenarioType
from app.domain.models.scenario import ScenarioComparison, ScenarioResult

DATE = "2026-07-17"


class FakeClient:
    """Returns a canned reply and records that it was called."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        return self.reply


class BoomClient:
    """Simulates the LLM being unavailable."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        raise RuntimeError("no azure")


# --- parsing / validation --------------------------------------------------


def test_extract_json_handles_code_fence_and_prose() -> None:
    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json_object('Here you go: {"a": 1}. Done.') == {"a": 1}
    assert extract_json_object("not json") is None


def test_validate_weights_drops_unknown_and_out_of_range() -> None:
    cleaned = _validate_weights(
        {
            "num_late": "5",  # coerced from string
            "total_tardiness": 3.7,  # rounded
            "makespan": -1,  # dropped (<= 0)
            "bogus_term": 9,  # dropped (unknown)
            "total_overtime": 10**9,  # clamped to WEIGHT_MAX
        }
    )
    assert cleaned == {
        "num_late": 5,
        "total_tardiness": 4,
        "total_overtime": WEIGHT_MAX,
    }
    assert set(cleaned).issubset(ALLOWED_TERMS)


# --- goal advisor ----------------------------------------------------------


def test_goal_advisor_returns_validated_weights() -> None:
    client = FakeClient(
        '{"is_goal": true, "weights": {"num_late": 2000000, "total_overtime": 2}, '
        '"strategy": "On-time first", "rationale": "Protect deliveries."}'
    )
    proposal = PlanningGoalAdvisor(client).propose_weights(
        "hit every order due date; overtime is fine"
    )
    assert proposal.usable is True
    assert proposal.fallback is False
    # LLM weights are kept, plus the compactness floor (makespan/tardiness).
    assert proposal.weights["num_late"] == 2000000
    assert proposal.weights["total_overtime"] == 2
    assert proposal.weights["makespan"] >= 5
    assert proposal.weights["total_tardiness"] >= 10
    assert proposal.strategy == "On-time first"


def test_goal_advisor_maps_goal_without_domain_keywords() -> None:
    # A valid goal phrased without any chat-classifier domain keyword must still
    # reach the model and be optimised (regression: was wrongly rejected).
    client = FakeClient('{"is_goal": true, "weights": {"makespan": 100}}')
    proposal = PlanningGoalAdvisor(client).propose_weights(
        "finish everything as fast as possible"
    )
    assert client.calls == 1
    assert proposal.usable is True


def test_goal_advisor_rejects_greeting_without_calling_llm() -> None:
    client = FakeClient('{"weights": {"num_late": 5}}')
    proposal = PlanningGoalAdvisor(client).propose_weights("hi")
    assert proposal.usable is False
    assert proposal.weights == {}
    assert client.calls == 0  # a greeting never reaches the LLM or the solver


def test_goal_advisor_replies_when_model_says_not_a_goal() -> None:
    client = FakeClient('{"is_goal": false, "message": "Please state a planning goal."}')
    proposal = PlanningGoalAdvisor(client).propose_weights("what's the weather today")
    assert proposal.usable is False
    assert proposal.rationale == "Please state a planning goal."


def test_goal_advisor_replies_on_unmappable_output() -> None:
    proposal = PlanningGoalAdvisor(FakeClient("total nonsense")).propose_weights(
        "do something clever"
    )
    assert proposal.usable is False  # no weights -> conversational reply, no plan


def test_goal_advisor_replies_when_llm_unavailable() -> None:
    proposal = PlanningGoalAdvisor(BoomClient()).propose_weights(
        "keep the production plan on schedule"
    )
    assert proposal.usable is False
    assert proposal.fallback is True


def test_goal_advisor_empty_goal_short_circuits() -> None:
    client = FakeClient("{}")
    proposal = PlanningGoalAdvisor(client).propose_weights("   ")
    assert proposal.usable is False
    assert client.calls == 0  # never calls the LLM for an empty goal


# --- scenario advisor ------------------------------------------------------


def _comparison() -> ScenarioComparison:
    baseline = ScenarioResult(
        scenario_type=ScenarioType.CURRENT_PLAN,
        name="Current Plan",
        kpis={"on_time_delivery_rate": 0.6, "total_tardiness_minutes": 900.0,
              "cost_total": 10000.0, "makespan_minutes": 500.0},
        is_baseline=True,
    )
    overtime = ScenarioResult(
        scenario_type=ScenarioType.OVERTIME_ENABLED,
        name="Overtime Enabled",
        kpis={"on_time_delivery_rate": 0.8, "total_tardiness_minutes": 300.0,
              "cost_total": 12000.0, "makespan_minutes": 460.0},
    )
    return ScenarioComparison(
        business_date=DATE,
        baseline_type=ScenarioType.CURRENT_PLAN,
        results=[baseline, overtime],
        kpi_deltas={"Overtime Enabled": {"on_time_delivery_rate": 0.2}},
    )


def test_scenario_advisor_uses_llm_choice() -> None:
    client = FakeClient(
        '{"recommended_type": "OVERTIME_ENABLED", '
        '"rationale": "Best OTD.", "considerations": ["Costs more"]}'
    )
    rec = ScenarioAdvisor(client).recommend(_comparison())
    assert rec.recommended_type == "OVERTIME_ENABLED"
    assert rec.recommended_name == "Overtime Enabled"
    assert rec.fallback is False


def test_scenario_advisor_rejects_unknown_type_and_falls_back() -> None:
    rec = ScenarioAdvisor(FakeClient('{"recommended_type": "NONSENSE"}')).recommend(
        _comparison()
    )
    # Deterministic fallback picks the highest-OTD scenario.
    assert rec.recommended_type == "OVERTIME_ENABLED"
    assert rec.fallback is True


def test_scenario_advisor_falls_back_when_llm_unavailable() -> None:
    rec = ScenarioAdvisor(BoomClient()).recommend(_comparison())
    assert rec.recommended_type == "OVERTIME_ENABLED"
    assert rec.fallback is True


# --- goal-outcome reasoning ------------------------------------------------


def test_outcome_explains_why_otd_did_not_move() -> None:
    from app.advisor.outcome import build_goal_outcome

    weights = {"num_late": 2000000, "makespan": 5, "total_tardiness": 10}
    before = {
        "on_time_delivery_rate": 0.554,
        "total_tardiness_minutes": 281 * 1440,
        "makespan_minutes": 12.7 * 1440,
        "cost_total": 277569.0,
        "scheduled_orders": 56.0,
        "late_orders": 25.0,
    }
    after = {
        "on_time_delivery_rate": 0.554,  # unchanged
        "total_tardiness_minutes": 174 * 1440,  # improved
        "makespan_minutes": 9.8 * 1440,  # improved
        "cost_total": 239038.0,  # improved
        "scheduled_orders": 56.0,
        "late_orders": 25.0,
    }
    text = build_goal_outcome(weights, before, after, _comparison())
    assert "structurally late" in text
    assert "cut total lateness" in text  # surfaces the real win


def test_outcome_reports_success_when_primary_kpi_improves() -> None:
    from app.advisor.outcome import build_goal_outcome

    weights = {"makespan": 100, "total_tardiness": 10}
    before = {"makespan_minutes": 18000.0}
    after = {"makespan_minutes": 14000.0}
    text = build_goal_outcome(weights, before, after, None)
    assert "worked" in text
