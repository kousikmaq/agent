"""Scenario advisor: recommend which solved what-if plan to commit.

Reads the day's already-solved :class:`ScenarioComparison` (KPIs + deltas) and
asks the LLM to recommend a single scenario, grounded ONLY on those numbers. It
changes nothing -- it is pure, read-only advice layered on top of the existing
comparison. If the model is unavailable, a deterministic pick (highest on-time
delivery, then least tardiness, then cheapest) is returned so the endpoint always
answers.
"""

from __future__ import annotations

from app.advisor.models import ScenarioRecommendation
from app.advisor.parsing import extract_json_object
from app.advisor.prompts import RECOMMEND_SYSTEM_PROMPT, build_recommend_prompt
from app.chat.azure_client import ChatCompletionClient
from app.core.logging import get_logger
from app.domain.models.scenario import ScenarioComparison, ScenarioResult

logger = get_logger(__name__)

# KPIs surfaced to the model (a readable subset of the full set).
_KPI_KEYS = (
    "on_time_delivery_rate",
    "total_tardiness_minutes",
    "makespan_minutes",
    "cost_total",
    "average_machine_utilization",
)


def _pick_best(results: list[ScenarioResult]) -> ScenarioResult | None:
    """Deterministic fallback: highest OTD, then least tardiness, then cheapest."""
    scored = [r for r in results if "on_time_delivery_rate" in r.kpis]
    if not scored:
        return results[0] if results else None

    def key(r: ScenarioResult) -> tuple[float, float, float, float]:
        return (
            -r.kpis.get("on_time_delivery_rate", 0.0),
            r.kpis.get("total_tardiness_minutes", float("inf")),
            r.kpis.get("cost_total", float("inf")),
            r.kpis.get("makespan_minutes", float("inf")),
        )

    return min(scored, key=key)


class ScenarioAdvisor:
    """Recommends the best scenario to commit from a solved comparison."""

    def __init__(self, client: ChatCompletionClient) -> None:
        self._client = client

    def recommend(self, comparison: ScenarioComparison) -> ScenarioRecommendation:
        """Recommend one scenario to commit for ``comparison``'s day."""
        results = list(comparison.results)
        names_by_type = {r.scenario_type.value: r.name for r in results}
        if not results:
            raise ValueError("Scenario comparison has no results to recommend from.")

        payload = [
            {
                "scenario_type": r.scenario_type.value,
                "name": r.name,
                "is_baseline": r.is_baseline,
                "kpis": {k: round(r.kpis[k], 4) for k in _KPI_KEYS if k in r.kpis},
                "deltas_vs_baseline": comparison.kpi_deltas.get(r.name, {}),
            }
            for r in results
        ]

        try:
            reply = self._client.complete(
                RECOMMEND_SYSTEM_PROMPT,
                build_recommend_prompt(comparison.business_date, payload),
            )
        except Exception as exc:  # noqa: BLE001 - never fail on LLM error
            logger.warning("Scenario advisor LLM call failed: %s", exc)
            return self._fallback(comparison, results)

        parsed = extract_json_object(reply) or {}
        rec_type = str(parsed.get("recommended_type", "")).strip()
        if rec_type not in names_by_type:
            logger.info("Scenario advisor returned unknown type %r; using fallback.", rec_type)
            return self._fallback(comparison, results)

        considerations = parsed.get("considerations") or []
        if not isinstance(considerations, list):
            considerations = [str(considerations)]

        return ScenarioRecommendation(
            business_date=comparison.business_date,
            recommended_type=rec_type,
            recommended_name=names_by_type[rec_type],
            rationale=str(parsed.get("rationale", "")).strip()
            or "Recommended based on the strongest on-time delivery and cost trade-off.",
            considerations=[str(c).strip() for c in considerations if str(c).strip()],
            fallback=False,
        )

    @staticmethod
    def _fallback(
        comparison: ScenarioComparison, results: list[ScenarioResult]
    ) -> ScenarioRecommendation:
        best = _pick_best(results)
        if best is None:  # pragma: no cover - guarded by caller
            raise ValueError("No scenarios available to recommend.")
        otd = best.kpis.get("on_time_delivery_rate")
        otd_txt = f"{otd:.0%}" if otd is not None else "the best available"
        return ScenarioRecommendation(
            business_date=comparison.business_date,
            recommended_type=best.scenario_type.value,
            recommended_name=best.name,
            rationale=(
                f"'{best.name}' delivers the most orders on time ({otd_txt}) with the "
                "least remaining lateness among the solved plans."
            ),
            considerations=[
                "Automatic pick (planning assistant unavailable); review the cost "
                "column before committing.",
            ],
            fallback=True,
        )
