"""
Workflow State Architecture (Layer A & B).
Defines explicit, inspectable Pydantic data models for workflow execution,
state transitions, tool interactions, verification results, and trajectory logging.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field
import time
import uuid


class PlanStep(BaseModel):
    step_id: int
    name: str
    description: str
    tool_required: Optional[str] = None
    expected_output: str
    status: Literal["pending", "in_progress", "completed", "failed", "skipped"] = "pending"
    result: Optional[str] = None


class Plan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    objective: str
    vulnerability_hypothesis: str
    target_invariants: List[str] = Field(default_factory=list)
    steps: List[PlanStep] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    replan_reason: Optional[str] = None


class ToolInvocation(BaseModel):
    tool_name: str
    input_args: Dict[str, Any]
    output_result: Any
    is_error: bool = False
    error_message: Optional[str] = None
    duration_ms: float = 0.0
    timestamp: float = Field(default_factory=time.time)


class VerificationCheck(BaseModel):
    check_name: str
    category: Literal["compilation", "exploit_neutralization", "invariant_preservation", "regression_freedom", "constraint_compliance"]
    passed: bool
    details: str
    diagnostics: Optional[Dict[str, Any]] = None


class VerificationReport(BaseModel):
    report_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: Literal["PASS", "FAIL"]
    checks: List[VerificationCheck] = Field(default_factory=list)
    failure_classification: Optional[Literal[
        "syntax_error",
        "exploit_not_neutralized",
        "invariant_violated",
        "regression_introduced",
        "interface_broken",
        "unknown"
    ]] = None
    actionable_feedback: str = ""
    suggested_fix_strategy: Optional[str] = None
    verified_at: float = Field(default_factory=time.time)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def total_count(self) -> int:
        return len(self.checks)


class ExecutionTrajectoryEntry(BaseModel):
    step_index: int
    stage: Literal["INITIAL_UNDERSTANDING", "PLANNING", "TOOL_EXECUTION", "PATCH_DRAFT", "VERIFICATION", "FEEDBACK_REPLAN", "TERMINATION"]
    agent: str
    action: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    state_delta: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class RemediationTask(BaseModel):
    task_id: str
    contract_name: str
    vulnerable_code: str
    vulnerability_description: str
    exploit_poc: str
    invariants: List[str] = Field(default_factory=list)
    regression_tests: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkflowState(BaseModel):
    task: RemediationTask
    user_context: Dict[str, Any] = Field(default_factory=dict)
    current_stage: Literal[
        "RECEIVED", "PLANNING", "EXECUTING", "VERIFYING", "REPLANNING", "SUCCESS", "FAILED"
    ] = "RECEIVED"
    plan: Optional[Plan] = None
    current_step_index: int = 0
    observations: List[str] = Field(default_factory=list)
    tool_results: List[ToolInvocation] = Field(default_factory=list)
    intermediate_outputs: Dict[str, Any] = Field(default_factory=dict)
    current_patch_code: Optional[str] = None
    verification_history: List[VerificationReport] = Field(default_factory=list)
    failures: List[Dict[str, Any]] = Field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    final_result: Optional[str] = None
    is_success: bool = False
    trajectory: List[ExecutionTrajectoryEntry] = Field(default_factory=list)
    started_at: float = Field(default_factory=time.time)
    finished_at: Optional[float] = None

    def log_trajectory(
        self,
        stage: Literal["INITIAL_UNDERSTANDING", "PLANNING", "TOOL_EXECUTION", "PATCH_DRAFT", "VERIFICATION", "FEEDBACK_REPLAN", "TERMINATION"],
        agent: str,
        action: str,
        inputs: Optional[Dict[str, Any]] = None,
        outputs: Optional[Dict[str, Any]] = None,
        state_delta: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = ExecutionTrajectoryEntry(
            step_index=len(self.trajectory) + 1,
            stage=stage,
            agent=agent,
            action=action,
            inputs=inputs or {},
            outputs=outputs or {},
            state_delta=state_delta or {},
            timestamp=time.time(),
        )
        self.trajectory.append(entry)

    def record_tool_call(self, invocation: ToolInvocation) -> None:
        self.tool_results.append(invocation)
        status_str = "ERROR" if invocation.is_error else "SUCCESS"
        self.observations.append(
            f"Tool '{invocation.tool_name}' returned ({status_str}): {str(invocation.output_result)[:200]}"
        )
