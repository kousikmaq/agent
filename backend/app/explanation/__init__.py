"""Explanation Context Builder.

Assembles a single, curated, structured context from Optimization, Analytics,
Risk, Recommendation, and Scenario outputs. This is the *only* seam that feeds
the LLM; the LLM can never reach the solver. No ML runs here.
"""

from __future__ import annotations

from app.explanation.context_builder import ExplanationContextBuilder
from app.explanation.schema import ExplanationSummary

__all__ = ["ExplanationContextBuilder", "ExplanationSummary"]
