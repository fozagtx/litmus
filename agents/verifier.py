"""
Verifier Agent (Layer B).
Performs independent multi-dimensional validation of proposed patches:
- Syntax & Compilation Integrity
- Exploit Neutralization PoC Execution
- Protocol Invariant Preservation
- Zero Functional Regressions

Generates structured VerificationReports with actionable feedback for replanning/retrying.
"""

from __future__ import annotations
import json
from typing import Dict, Any, Optional
from agents.base import BaseAgent
from workflow.state import WorkflowState, VerificationReport, VerificationCheck
from tools.contract_compiler import ContractCompilerTool
from tools.exploit_runner import ExploitRunnerTool
from tools.invariant_checker import InvariantCheckerTool
from prompts.verification_prompts import VERIFIER_SYSTEM_PROMPT, VERIFIER_EVAL_PROMPT_TEMPLATE


class VerifierAgent(BaseAgent):
    def __init__(self, model_name: str = "gpt-4o"):
        super().__init__(model_name=model_name, temperature=0.0)
        self.compiler = ContractCompilerTool()
        self.exploit_runner = ExploitRunnerTool()
        self.invariant_checker = InvariantCheckerTool()

    def verify_patch(self, state: WorkflowState) -> VerificationReport:
        candidate_code = state.current_patch_code or state.task.vulnerable_code
        task = state.task
        checks = []

        # 1. Compilation Check
        comp_res = self.compiler.execute(source_code=candidate_code)
        comp_passed = comp_res.output.get("compiled_successfully", False) if comp_res.success else False
        comp_details = "Code compiled successfully with zero syntax errors." if comp_passed else f"Errors: {comp_res.output.get('errors', [])}"
        checks.append(VerificationCheck(
            check_name="Solidity Compilation & Syntax Check",
            category="compilation",
            passed=comp_passed,
            details=comp_details,
            diagnostics=comp_res.output if comp_res.success else {"error": comp_res.error}
        ))

        # 2. Exploit Neutralization Check
        exploit_res = self.exploit_runner.execute(
            source_code=candidate_code,
            exploit_type=task.metadata.get("vulnerability_type", "REENTRANCY"),
            exploit_poc=task.exploit_poc
        )
        exploit_passed = exploit_res.output.get("exploit_neutralized", False) if exploit_res.success else False
        exploit_diag = exploit_res.output.get("diagnostics", "Exploit check completed") if exploit_res.success else "Exploit runner error"
        checks.append(VerificationCheck(
            check_name="Exploit Proof-of-Concept Neutralization",
            category="exploit_neutralization",
            passed=exploit_passed,
            details=exploit_diag,
            diagnostics=exploit_res.output if exploit_res.success else {"error": exploit_res.error}
        ))

        # 3. Protocol Invariant & Regression Suite
        inv_res = self.invariant_checker.execute(
            source_code=candidate_code,
            invariants=task.invariants,
            regression_tests=task.regression_tests
        )
        inv_passed = inv_res.output.get("all_passed", False) if inv_res.success else False
        inv_summary = inv_res.output.get("summary", "Invariants checked") if inv_res.success else "Invariant checker error"
        checks.append(VerificationCheck(
            check_name="Protocol Invariant & Regression Suite",
            category="invariant_preservation",
            passed=inv_passed,
            details=inv_summary,
            diagnostics=inv_res.output if inv_res.success else {"error": inv_res.error}
        ))

        # Determine overall PASS / FAIL
        all_passed = comp_passed and exploit_passed and inv_passed
        status = "PASS" if all_passed else "FAIL"

        failure_classification = None
        feedback = "All checks passed. Patch meets all verification criteria."
        fix_strategy = None

        if not comp_passed:
            failure_classification = "syntax_error"
            feedback = f"Patch failed compilation: {comp_details}"
            fix_strategy = "Fix syntax errors, ensure matching braces and correct visibility qualifiers."
        elif not exploit_passed:
            failure_classification = "exploit_not_neutralized"
            feedback = f"Exploit simulation succeeded against patch: {exploit_diag}"
            fix_strategy = "Ensure Checks-Effects-Interactions pattern is strictly applied before external calls, or add nonReentrant guard."
        elif not inv_passed:
            failure_classification = "invariant_violated"
            failures = inv_res.output.get("failures", [])
            fail_desc = "; ".join([f"{f.get('test_name')}: {f.get('detail')}" for f in failures])
            feedback = f"Protocol invariants violated: {fail_desc}"
            fix_strategy = "Preserve standard user functions and ensure balance solvency tracking is not broken."

        report = VerificationReport(
            status=status,
            checks=checks,
            failure_classification=failure_classification,
            actionable_feedback=feedback,
            suggested_fix_strategy=fix_strategy
        )

        state.verification_history.append(report)
        return report
