"""Scenario catalog.

Binds each predefined :class:`ScenarioType` to its human-readable definition
and the transform that realises it. New scenarios are added here without
changing the engine (Open/Closed Principle).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.domain.enums import ScenarioType
from app.domain.models.factory_state import FactoryState
from app.domain.models.scenario import ScenarioDefinition
from app.scenario.transforms import (
    apply_additional_shift,
    apply_alternate_machines,
    apply_current_plan,
    apply_overtime,
)

# A transform maps (state_clone, parameters) -> transformed state.
ScenarioTransform = Callable[[FactoryState, dict[str, Any]], FactoryState]


@dataclass(frozen=True)
class ScenarioSpec:
    """A scenario definition paired with its transform and baseline flag."""

    definition: ScenarioDefinition
    transform: ScenarioTransform
    is_baseline: bool = False


DEFAULT_SCENARIOS: tuple[ScenarioSpec, ...] = (
    ScenarioSpec(
        definition=ScenarioDefinition(
            scenario_type=ScenarioType.CURRENT_PLAN,
            name="Current Plan",
            description="The baseline schedule with no changes applied.",
            parameters={},
        ),
        transform=apply_current_plan,
        is_baseline=True,
    ),
    ScenarioSpec(
        definition=ScenarioDefinition(
            scenario_type=ScenarioType.OVERTIME_ENABLED,
            name="Overtime Enabled",
            description=(
                "Extend the working window earlier and enable worker overtime to "
                "start production sooner."
            ),
            parameters={},
        ),
        transform=apply_overtime,
    ),
    ScenarioSpec(
        definition=ScenarioDefinition(
            scenario_type=ScenarioType.ALTERNATE_MACHINES,
            name="Alternate Machines",
            description=(
                "Return down machines to service as backups and clear breakdown "
                "maintenance to widen the usable machine pool."
            ),
            parameters={},
        ),
        transform=apply_alternate_machines,
    ),
    ScenarioSpec(
        definition=ScenarioDefinition(
            scenario_type=ScenarioType.ADDITIONAL_SHIFT,
            name="Additional Shift",
            description=(
                "Add a parallel night-shift machine per machine to increase "
                "capacity and parallelism."
            ),
            parameters={"suffix": "-N"},
        ),
        transform=apply_additional_shift,
    ),
)
