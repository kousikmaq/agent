"""
Placeholders for the not-yet-built features. They return a clear, honest
"planned" response so the UI and the agent can already show the full roadmap.
"""
from logging_config import get_logger

log = get_logger("stubs")

PLANNED = {
    "demand_vs_capacity": "Rough-cut demand vs capacity verdict + cheapest way to close the gap.",
}


def stub(feature_key: str) -> dict:
    log.info("Feature '%s' requested but not yet implemented (returning planned stub).", feature_key)
    return {
        "feature": feature_key,
        "status": "planned",
        "message": PLANNED.get(feature_key, "Planned feature."),
    }
