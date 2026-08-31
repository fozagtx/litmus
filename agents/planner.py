"""
Planner Agent (Layer A).
Decomposes vulnerability remediation into structured execution steps,
identifies target invariants, and formulates replanning strategies on verification rejection.
"""

from __future__ import annotations
import json
from typing import Dict, Any, Optional
from agents.base import BaseAgent
from workflow.state import Plan, PlanStep, RemediationTask, VerificationReport
from prompts.planning_prompts import (
    PLANNER_SYSTEM_PROMPT,
    PLANNER_USER_PROMPT_TEMPLATE,
    REPLAN_PROMPT_TEMPLATE
)


class PlannerAgent(BaseAgent):
    def __init__(self, model_name: str = "gpt-4o"):
        super().__init__(model_name=model_name, temperature=0.1)

    def generate_plan(self, task: RemediationTask) -> Plan:
        user_prompt = PLANNER_USER_PROMPT_TEMPLATE.format(
            contract_name=task.contract_name,
            vulnerability_description=task.vulnerability_description,
            exploit_poc=task.exploit_poc,
            invariants="\n".join(f"- {inv}" for inv in task.invariants),
            vulnerable_code=task.vulnerable_code
        )

        raw_resp = self.call_llm(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_format_json=True
        )

        try:
            data = json.loads(raw_resp)
            steps = [
                PlanStep(
                    step_id=s.get("step_id", idx + 1),
                    name=s.get("name", f"Step {idx + 1}"),
                    description=s.get("description", ""),
                    tool_required=s.get("tool_required"),
                    expected_output=s.get("expected_output", "")
                )
                for idx, s in enumerate(data.get("steps", []))
            ]
            return Plan(
                objective=data.get("objective", "Remediate smart contract vulnerability"),
                vulnerability_hypothesis=data.get("vulnerability_hypothesis", ""),
                target_invariants=data.get("target_invariants", task.invariants),
                steps=steps
            )
        except Exception:
            # Default structured plan
            return Plan(
                objective=f"Remediate {task.contract_name} security vulnerability",
                vulnerability_hypothesis=task.vulnerability_description,
                target_invariants=task.invariants,
                steps=[
                    PlanStep(step_id=1, name="Deconstruct AST", description="Parse contract AST and function boundaries", tool_required="ast_parser", expected_output="Parsed AST"),
                    PlanStep(step_id=2, name="Run Static Analysis", description="Identify vulnerability locations and anti-patterns", tool_required="static_analyzer", expected_output="Static findings"),
                    PlanStep(step_id=3, name="Synthesize Patch", description="Draft secure replacement code", tool_required="patch_tool", expected_output="Candidate patch code")
                ]
            )

    def replan(self, task: RemediationTask, failed_report: VerificationReport) -> Plan:
        replan_prompt = REPLAN_PROMPT_TEMPLATE.format(
            verification_diagnostics=failed_report.actionable_feedback,
            actionable_feedback=failed_report.suggested_fix_strategy or "Address failed invariant checks",
            failures="\n".join([f"- {c.check_name}: {c.details}" for c in failed_report.checks if not c.passed])
        )

        raw_resp = self.call_llm(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_prompt=replan_prompt,
            response_format_json=True
        )

        try:
            data = json.loads(raw_resp)
            steps = [
                PlanStep(
                    step_id=s.get("step_id", idx + 1),
                    name=s.get("name", f"Replan Step {idx + 1}"),
                    description=s.get("description", ""),
                    tool_required=s.get("tool_required"),
                    expected_output=s.get("expected_output", "")
                )
                for idx, s in enumerate(data.get("steps", []))
            ]
            return Plan(
                objective=data.get("objective", f"Targeted Repair: {failed_report.failure_classification}"),
                vulnerability_hypothesis=data.get("vulnerability_hypothesis", failed_report.actionable_feedback),
                target_invariants=data.get("target_invariants", task.invariants),
                steps=steps,
                replan_reason=failed_report.failure_classification
            )
        except Exception:
            return Plan(
                objective=f"Targeted Repair: {failed_report.failure_classification}",
                vulnerability_hypothesis=failed_report.actionable_feedback,
                target_invariants=task.invariants,
                steps=[
                    PlanStep(step_id=1, name="Analyze Verification Feedback", description="Extract root cause of verification failure", tool_required="static_analyzer", expected_output="Failure analysis"),
                    PlanStep(step_id=2, name="Synthesize Corrected Patch", description="Apply targeted correction to fix failed invariants", tool_required="patch_tool", expected_output="Corrected patch")
                ],
                replan_reason=failed_report.failure_classification
            )
