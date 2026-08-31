"""
Unit Tests for Workflow State & Trajectory Models.
"""

import pytest
from workflow.state import (
    WorkflowState,
    RemediationTask,
    Plan,
    PlanStep,
    ToolInvocation,
    VerificationReport,
    VerificationCheck,
    ExecutionTrajectoryEntry,
)


def test_remediation_task_creation():
    task = RemediationTask(
        task_id="case_01",
        contract_name="EtherVault",
        vulnerable_code="contract EtherVault {}",
        vulnerability_description="Reentrancy flaw",
        exploit_poc="contract Attacker {}",
        invariants=["Solvency", "User access"],
        regression_tests=[{"name": "test_withdraw", "function_called": "withdraw"}]
    )
    assert task.task_id == "case_01"
    assert len(task.invariants) == 2
    assert len(task.regression_tests) == 1


def test_workflow_state_trajectory_logging():
    task = RemediationTask(
        task_id="case_01",
        contract_name="EtherVault",
        vulnerable_code="contract EtherVault {}",
        vulnerability_description="Reentrancy flaw",
        exploit_poc="contract Attacker {}"
    )
    state = WorkflowState(task=task)
    assert state.current_stage == "RECEIVED"
    assert len(state.trajectory) == 0

    state.log_trajectory(
        stage="INITIAL_UNDERSTANDING",
        agent="Orchestrator",
        action="Task received",
        inputs={"task_id": "case_01"}
    )
    assert len(state.trajectory) == 1
    assert state.trajectory[0].stage == "INITIAL_UNDERSTANDING"
    assert state.trajectory[0].agent == "Orchestrator"


def test_tool_invocation_recording():
    task = RemediationTask(
        task_id="case_01",
        contract_name="EtherVault",
        vulnerable_code="contract EtherVault {}",
        vulnerability_description="Reentrancy flaw",
        exploit_poc="contract Attacker {}"
    )
    state = WorkflowState(task=task)
    inv = ToolInvocation(
        tool_name="ast_parser",
        input_args={"source_code": "contract Test {}"},
        output_result={"contracts": ["Test"]},
        is_error=False,
        duration_ms=1.5
    )
    state.record_tool_call(inv)
    assert len(state.tool_results) == 1
    assert len(state.observations) == 1
    assert "ast_parser" in state.observations[0]
