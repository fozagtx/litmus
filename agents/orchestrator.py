"""
Orchestrator Agent (Layer A).
Coordinates the complete agentic remediation lifecycle:
Task Reception -> Planning -> Tool Execution -> Patch Synthesis -> Verification -> Replan/Retry Loop.
"""

from __future__ import annotations
import time
from typing import Dict, Any, Optional
from workflow.state import WorkflowState, RemediationTask
from agents.planner import PlannerAgent
from agents.executor import ExecutorAgent
from agents.verifier import VerifierAgent


class OrchestratorAgent:
    def __init__(
        self,
        planner: Optional[PlannerAgent] = None,
        executor: Optional[ExecutorAgent] = None,
        verifier: Optional[VerifierAgent] = None,
        max_retries: int = 3
    ):
        self.planner = planner or PlannerAgent()
        self.executor = executor or ExecutorAgent()
        self.verifier = verifier or VerifierAgent()
        self.max_retries = max_retries

    def run(self, task: RemediationTask) -> WorkflowState:
        state = WorkflowState(
            task=task,
            max_retries=self.max_retries,
            current_stage="RECEIVED",
            started_at=time.time()
        )

        # Stage 1: Initial Understanding
        state.log_trajectory(
            stage="INITIAL_UNDERSTANDING",
            agent="Orchestrator",
            action="Received remediation task and initialized state",
            inputs={"contract": task.contract_name, "vulnerability": task.vulnerability_description}
        )

        # Stage 2: Initial Planning
        state.current_stage = "PLANNING"
        plan = self.planner.generate_plan(task)
        state.plan = plan
        state.log_trajectory(
            stage="PLANNING",
            agent="PlannerAgent",
            action="Generated structured remediation plan",
            outputs={"plan_id": plan.plan_id, "step_count": len(plan.steps), "objective": plan.objective}
        )

        # Main Execution & Verification Loop
        while state.retry_count <= state.max_retries:
            state.current_stage = "EXECUTING"

            # Stage 3: Step-by-step Tool Execution
            for step_idx, step in enumerate(state.plan.steps):
                state.current_step_index = step_idx
                step_res = self.executor.execute_step(state, step)
                state.log_trajectory(
                    stage="TOOL_EXECUTION",
                    agent="ExecutorAgent",
                    action=f"Executed Step {step.step_id}: {step.name}",
                    inputs={"tool": step.tool_required, "desc": step.description},
                    outputs={"result": step_res[:200]}
                )

            # Stage 4: Patch Synthesis
            candidate_patch = state.current_patch_code or state.task.vulnerable_code
            state.log_trajectory(
                stage="PATCH_DRAFT",
                agent="ExecutorAgent",
                action="Synthesized candidate patch code",
                outputs={"patch_lines": len(candidate_patch.splitlines())}
            )

            # Stage 5: Independent Verification (Layer B)
            state.current_stage = "VERIFYING"
            report = self.verifier.verify_patch(state)
            state.log_trajectory(
                stage="VERIFICATION",
                agent="VerifierAgent",
                action=f"Independent Verification Completed: {report.status}",
                outputs={
                    "status": report.status,
                    "checks_passed": f"{report.passed_count}/{report.total_count}",
                    "failure_classification": report.failure_classification,
                    "actionable_feedback": report.actionable_feedback
                }
            )

            if report.status == "PASS":
                state.current_stage = "SUCCESS"
                state.is_success = True
                state.final_result = candidate_patch
                state.finished_at = time.time()
                state.log_trajectory(
                    stage="TERMINATION",
                    agent="Orchestrator",
                    action="Workflow completed successfully. Patch verified.",
                    outputs={"status": "SUCCESS", "retries": state.retry_count}
                )
                return state

            # If Verification Failed: Check Retry Budget
            state.retry_count += 1
            if state.retry_count > state.max_retries:
                state.current_stage = "FAILED"
                state.is_success = False
                state.final_result = candidate_patch
                state.finished_at = time.time()
                state.log_trajectory(
                    stage="TERMINATION",
                    agent="Orchestrator",
                    action=f"Workflow exceeded maximum retries ({state.max_retries}). Failed verification.",
                    outputs={"status": "FAILED", "last_failure": report.failure_classification}
                )
                return state

            # Stage 6: Replan & Feedback Loop
            state.current_stage = "REPLANNING"
            state.log_trajectory(
                stage="FEEDBACK_REPLAN",
                agent="Orchestrator",
                action=f"Initiating Retry #{state.retry_count} with verifier diagnostic feedback",
                inputs={
                    "retry_number": state.retry_count,
                    "failure_classification": report.failure_classification,
                    "feedback": report.actionable_feedback
                }
            )
            state.plan = self.planner.replan(task, report)

        state.finished_at = time.time()
        return state
