"""
Benchmark Scorer & Independent Evaluator (Layer C).
Evaluates candidate patches across the 4 core dimensions:
1. Compilation
2. Exploit Neutralization
3. Invariant Preservation
4. Zero Regressions
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
from benchmark.schema import BenchmarkCase
from evaluation.metrics import CaseEvaluationResult
from tools.contract_compiler import ContractCompilerTool
from tools.exploit_runner import ExploitRunnerTool
from tools.invariant_checker import InvariantCheckerTool


class BenchmarkScorer:
    def __init__(self):
        self.compiler = ContractCompilerTool()
        self.exploit_runner = ExploitRunnerTool()
        self.invariant_checker = InvariantCheckerTool()

    def evaluate_case(
        self,
        case: BenchmarkCase,
        patch_code: str,
        version: str = "v_unknown",
        retry_count: int = 0,
        duration_seconds: float = 0.0,
        cost_usd: float = 0.0,
        tool_calls_count: int = 0
    ) -> CaseEvaluationResult:
        failure_reasons = []

        # 1. Compilation Check
        comp_res = self.compiler.execute(source_code=patch_code)
        comp_output = comp_res.output if comp_res.success else {}
        comp_passed = comp_output.get("compiled_successfully", False)
        if not comp_passed:
            errs = comp_output.get("errors", ["Unknown compilation error"])
            failure_reasons.append(f"Compilation Failed: {'; '.join(errs[:2])}")

        # 2. Exploit Neutralization Check
        exploit_res = self.exploit_runner.execute(
            source_code=patch_code,
            exploit_type=case.vulnerability_type,
            exploit_poc=case.exploit_poc
        )
        exploit_output = exploit_res.output if exploit_res.success else {}
        exploit_neutralized = exploit_output.get("exploit_neutralized", False)
        if not exploit_neutralized:
            diag = exploit_output.get("diagnostics", "Exploit succeeded against patched contract")
            failure_reasons.append(f"Exploit Neutralization Failed: {diag}")

        # 3. Invariant & Regression Checks
        reg_tests_dict = [r.model_dump() for r in case.regression_tests]
        inv_res = self.invariant_checker.execute(
            source_code=patch_code,
            invariants=case.invariants,
            regression_tests=reg_tests_dict
        )
        inv_output = inv_res.output if inv_res.success else {}
        inv_passed_cnt = inv_output.get("invariants_passed", 0)
        inv_total_cnt = inv_output.get("invariants_total", len(case.invariants))
        reg_passed_cnt = inv_output.get("regressions_passed", 0)
        reg_total_cnt = inv_output.get("regressions_total", len(case.regression_tests))

        all_invariants_passed = (inv_passed_cnt == inv_total_cnt) if inv_total_cnt > 0 else True
        zero_regressions = (reg_passed_cnt == reg_total_cnt) if reg_total_cnt > 0 else True

        if not all_invariants_passed or not zero_regressions:
            fails = inv_output.get("failures", [])
            for f in fails:
                failure_reasons.append(f"{f.get('type')}: {f.get('detail')}")

        # Primary Metric: All dimensions must pass
        is_success = (
            comp_passed and
            exploit_neutralized and
            all_invariants_passed and
            zero_regressions
        )

        return CaseEvaluationResult(
            case_id=case.case_id,
            version=version,
            patch_code=patch_code,
            compilation_passed=comp_passed,
            exploit_neutralized=exploit_neutralized,
            invariants_passed=inv_passed_cnt,
            invariants_total=inv_total_cnt,
            regressions_passed=reg_passed_cnt,
            regressions_total=reg_total_cnt,
            all_invariants_passed=all_invariants_passed,
            zero_regressions=zero_regressions,
            is_success=is_success,
            failure_reasons=failure_reasons,
            retry_count=retry_count,
            duration_seconds=duration_seconds,
            cost_usd=cost_usd,
            tool_calls_count=tool_calls_count
        )
