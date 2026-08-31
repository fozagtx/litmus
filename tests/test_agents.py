"""
Unit & Integration Tests for Agents & Orchestrator.
"""

import pytest
from workflow.state import RemediationTask
from agents.planner import PlannerAgent
from agents.executor import ExecutorAgent
from agents.verifier import VerifierAgent
from agents.orchestrator import OrchestratorAgent


@pytest.fixture
def sample_task():
    return RemediationTask(
        task_id="case_01",
        contract_name="EtherVault",
        vulnerable_code="""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
contract EtherVault {
    mapping(address => uint256) public balances;
    function withdraw() external {
        (bool s, ) = msg.sender.call{value: balances[msg.sender]}("");
        balances[msg.sender] = 0;
    }
}""",
        vulnerability_description="Reentrancy flaw in withdraw()",
        exploit_poc="Attacker drains contract recursively",
        invariants=["Solvency: sum(balances) <= address(this).balance", "Legitimate user withdrawal"],
        regression_tests=[{"name": "test_withdraw", "function_called": "withdraw"}],
        metadata={"vulnerability_type": "REENTRANCY"}
    )


def test_planner_agent(sample_task):
    planner = PlannerAgent()
    plan = planner.generate_plan(sample_task)
    assert plan.objective is not None
    assert len(plan.steps) >= 2


def test_verifier_agent_rejection_and_acceptance(sample_task):
    verifier = VerifierAgent()
    from workflow.state import WorkflowState
    
    # Flawed patch state
    state_flawed = WorkflowState(task=sample_task, current_patch_code=sample_task.vulnerable_code)
    report_flawed = verifier.verify_patch(state_flawed)
    assert report_flawed.status == "FAIL"
    assert report_flawed.failure_classification == "exploit_not_neutralized"

    # Secure patch state
    secure_code = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
contract EtherVault {
    mapping(address => uint256) public balances;
    function withdraw() external {
        balances[msg.sender] = 0;
        (bool s, ) = msg.sender.call{value: 1}("");
    }
}"""
    state_secure = WorkflowState(task=sample_task, current_patch_code=secure_code)
    report_secure = verifier.verify_patch(state_secure)
    assert report_secure.status == "PASS"


def test_orchestrator_end_to_end(sample_task):
    orchestrator = OrchestratorAgent(max_retries=3)
    final_state = orchestrator.run(sample_task)
    assert final_state.current_stage == "SUCCESS"
    assert final_state.is_success is True
    assert final_state.final_result is not None
    assert len(final_state.trajectory) >= 4
