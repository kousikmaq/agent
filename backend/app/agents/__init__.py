"""MAF orchestration layer.

A thin orchestration layer that coordinates the existing deterministic services
as strongly-typed agents. This package contains **no business logic** - each
agent is a wrapper that (in later phases) delegates to an existing engine. The
OR-Tools scheduler, analytics, risk, recommendation, scenario, and explanation
modules remain unchanged; MAF only sequences them.

Phase 1 provides the foundation (base agent, contracts, context, retry, trace,
timing, DI) and a workflow skeleton with mock agents that return success.
"""

from __future__ import annotations

from app.agents.base import AgentResult, AgentStatus, BaseAgent
from app.agents.context import WorkflowContext, WorkflowState
from app.agents.orchestrator import WorkflowOrchestrator, WorkflowRunResult
from app.agents.workflow import AgentWorkflow

__all__ = [
    "BaseAgent",
    "AgentResult",
    "AgentStatus",
    "WorkflowContext",
    "WorkflowState",
    "AgentWorkflow",
    "WorkflowOrchestrator",
    "WorkflowRunResult",
]
