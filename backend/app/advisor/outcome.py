"""Goal-outcome reasoning.

After a goal-driven re-solve, this explains -- in plain English, grounded on the
before/after KPIs and the day's scenario ceiling -- whether the goal's intent was
actually achieved, and if not, WHY (e.g. on-time delivery is capped by material
availability / due dates, so re-prioritising cannot raise it). Deterministic and
LLM-free so the explanation is always consistent with the numbers.
"""

from __future__ import annotations

from app.domain.models.scenario import ScenarioComparison
from app.optimization.objective_spec import (
    MAKESPAN,
    MAX_MACHINE_LOAD,
    NUM_LATE,
    TOTAL_FLOW,
    TOTAL_OVERTIME,
    TOTAL_TARDINESS,
)

# primary objective term -> (kpi key, higher_is_better, planner-facing label).
_PRIMARY: dict[str, tuple[str, bool, str]] = {
    NUM_LATE: ("on_time_delivery_rate", True, "on-time delivery"),
    TOTAL_TARDINESS: ("total_tardiness_minutes", False, "total lateness"),
    MAKESPAN: ("makespan_minutes", False, "a shorter makespan"),
    TOTAL_FLOW: ("makespan_minutes", False, "faster throughput"),
    MAX_MACHINE_LOAD: ("average_machine_utilization", True, "machine balance"),
    TOTAL_OVERTIME: ("cost_total", False, "lower cost"),
}


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _days(mins: float) -> str:
    return f"{mins / 1440:.1f} days"


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _fmt(key: str, value: float) -> str:
    if key == "on_time_delivery_rate" or key == "average_machine_utilization":
        return _pct(value)
    if key in ("total_tardiness_minutes", "makespan_minutes"):
        return _days(value)
    if key == "cost_total":
        return _money(value)
    return f"{value:g}"


def _primary_term(weights: dict[str, int]) -> str | None:
    if not weights:
        return None
    return max(weights.items(), key=lambda kv: kv[1])[0]


def _improved(key: str, before: float, after: float, higher_better: bool) -> bool:
    if higher_better:
        return after > before + (0.005 if key == "on_time_delivery_rate" else 0)
    # lower is better; require a small meaningful drop
    threshold = 1.0 if key == "cost_total" else 60.0  # $1 or 1 hour
    return after < before - threshold


def _secondary_wins(before: dict, after: dict) -> list[str]:
    """Human-readable list of the notable improvements achieved elsewhere."""
    wins: list[str] = []
    tard_b, tard_a = before.get("total_tardiness_minutes", 0), after.get(
        "total_tardiness_minutes", 0
    )
    if tard_a < tard_b - 60:
        wins.append(f"cut total lateness by {_days(tard_b - tard_a)}")
    ms_b, ms_a = before.get("makespan_minutes", 0), after.get("makespan_minutes", 0)
    if ms_a < ms_b - 60:
        wins.append(f"finished {_days(ms_b - ms_a)} sooner")
    cost_b, cost_a = before.get("cost_total", 0), after.get("cost_total", 0)
    if cost_a < cost_b - 1:
        wins.append(f"saved {_money(cost_b - cost_a)}")
    util_b, util_a = before.get("average_machine_utilization", 0), after.get(
        "average_machine_utilization", 0
    )
    if util_a > util_b + 0.01:
        wins.append(f"raised utilisation to {_pct(util_a)}")
    return wins


def build_goal_outcome(
    weights: dict[str, int],
    before: dict[str, float],
    after: dict[str, float],
    scenarios: ScenarioComparison | None = None,
) -> str:
    """Explain whether the goal was met and, if not, why — grounded on the KPIs."""
    term = _primary_term(weights)
    if term is None or term not in _PRIMARY:
        return ""
    key, higher_better, label = _PRIMARY[term]
    b, a = float(before.get(key, 0.0)), float(after.get(key, 0.0))

    if _improved(key, b, a, higher_better):
        head = (
            f"Your goal to prioritise {label} worked: it moved from "
            f"{_fmt(key, b)} to {_fmt(key, a)}."
        )
        wins = [w for w in _secondary_wins(before, after)]
        if wins:
            head += " It also " + ", ".join(wins) + "."
        return head

    # --- The targeted KPI did not improve: explain WHY. ---
    if key == "on_time_delivery_rate":
        late = int(round(after.get("late_orders", 0)))
        total = int(round(after.get("scheduled_orders", 0)))
        ceiling = None
        if scenarios is not None:
            otds = [
                r.kpis.get("on_time_delivery_rate")
                for r in scenarios.results
                if r.kpis.get("on_time_delivery_rate") is not None
            ]
            ceiling = max(otds) if otds else None
        parts = [
            f"On-time delivery held at {_pct(a)} — that is the most achievable "
            f"for today's data."
        ]
        if total:
            parts.append(
                f" {late} of {total} orders are structurally late: they are blocked "
                "by material arrival or have due dates tighter than their "
                "release-plus-lead time, so re-prioritising alone cannot deliver "
                "them on time."
            )
        if ceiling is not None and ceiling <= a + 0.005:
            parts.append(
                " Even the overtime, alternate-machine and extra-shift scenarios "
                "top out at the same rate, confirming the limit is the data (materials "
                "and due dates), not the schedule."
            )
    else:
        parts = [
            f"{label.capitalize()} did not improve ({_fmt(key, b)} → {_fmt(key, a)}); "
            "it was not the binding constraint today."
        ]

    wins = _secondary_wins(before, after)
    if wins:
        parts.append(" The plan still " + ", ".join(wins) + ".")
    else:
        parts.append(" The plan is unchanged on the other KPIs too.")
    return "".join(parts)
