"""Planning-advisor DTOs.

Response structures produced by the LLM planning advisor. The advisor turns a
planner's natural-language *intent* into solver inputs (objective weights) and
turns a solved scenario comparison into a plain-English *recommendation*. It
never produces a schedule itself -- the CP-SAT solver remains the sole source of
plans, so every guarantee (feasibility, determinism, auditability) is preserved.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WeightProposal(BaseModel):
    """A validated objective-weight set derived from a planner's goal.

    ``weights`` is guaranteed to contain only known objective-term names with
    non-negative integer weights (validated in :mod:`app.advisor.goal_advisor`),
    so it is always safe to hand straight to the solver.
    """

    goal: str = Field(..., description="The planner's natural-language goal.")
    weights: dict[str, int] = Field(
        ..., description="Validated objective term -> weight (all minimised)."
    )
    strategy: str = Field(
        default="",
        description="Short label for the strategy (e.g. 'On-time first, then cost').",
    )
    rationale: str = Field(
        default="",
        description="Plain-English explanation of why these weights fit the goal.",
    )
    usable: bool = Field(
        default=True,
        description="False when the text is not a real planning goal (e.g. a greeting).",
    )
    fallback: bool = Field(
        default=False,
        description="True when the goal could not be parsed and defaults were used.",
    )


class ScenarioRecommendation(BaseModel):
    """The advisor's recommendation of which scenario to commit."""

    business_date: str = Field(..., description="Day the recommendation applies to.")
    recommended_type: str = Field(
        ..., description="ScenarioType recommended as the plan to use."
    )
    recommended_name: str = Field(
        ..., description="Human-readable name of the recommended scenario."
    )
    rationale: str = Field(
        ..., description="Plain-English justification grounded on the KPI deltas."
    )
    considerations: list[str] = Field(
        default_factory=list,
        description="Trade-offs the planner should weigh before committing.",
    )
    fallback: bool = Field(
        default=False,
        description="True when the LLM was unavailable and a deterministic pick was used.",
    )
