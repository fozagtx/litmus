"""
Workflow Execution Module.
Provides execution dispatch and observation logging.
"""

from __future__ import annotations
from typing import TYPE_CHECKING
from workflow.state import WorkflowState, PlanStep

if TYPE_CHECKING:
    from agents.executor import ExecutorAgent


def execute_plan_step(state: WorkflowState, step: PlanStep, executor: ExecutorAgent = None) -> str:
    if executor is None:
        from agents.executor import ExecutorAgent
        executor = ExecutorAgent()
    return executor.execute_step(state, step)
