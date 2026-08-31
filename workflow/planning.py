"""
Workflow Planning Module.
Provides planning helpers and validation logic.
"""

from __future__ import annotations
from typing import TYPE_CHECKING
from workflow.state import Plan, PlanStep, RemediationTask

if TYPE_CHECKING:
    from agents.planner import PlannerAgent


def create_remediation_plan(task: RemediationTask, planner: PlannerAgent = None) -> Plan:
    if planner is None:
        from agents.planner import PlannerAgent
        planner = PlannerAgent()
    return planner.generate_plan(task)
