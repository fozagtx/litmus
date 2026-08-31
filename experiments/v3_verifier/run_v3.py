"""
Experiment V3: Verifier Gate without Retry Loop.
Hypothesis: Adding the Layer B Verifier prevents flawed patches from being deployed (zero false-claim rate),
but without an autonomous retry/re-planning loop, rejected edge cases terminate immediately in failure.
"""

from __future__ import annotations
import time
from typing import List
from benchmark.loader import load_benchmark
from benchmark.schema import BenchmarkCase
from evaluation.metrics import CaseEvaluationResult
from evaluation.scorer import BenchmarkScorer
from workflow.state import RemediationTask, WorkflowState
from agents.planner import PlannerAgent
from agents.executor import ExecutorAgent
from agents.verifier import VerifierAgent


def run_v3_experiment() -> List[CaseEvaluationResult]:
    suite = load_benchmark()
    planner = PlannerAgent()
    executor = ExecutorAgent()
    verifier = VerifierAgent()
    scorer = BenchmarkScorer()
    results: List[CaseEvaluationResult] = []

    for case in suite.cases:
        start_time = time.perf_counter()
        task = RemediationTask(
            task_id=case.case_id,
            contract_name=case.title,
            vulnerable_code=case.vulnerable_code,
            vulnerability_description=case.vulnerability_description,
            exploit_poc=case.exploit_poc,
            invariants=case.invariants,
            regression_tests=[r.model_dump() for r in case.regression_tests],
            metadata={"vulnerability_type": case.vulnerability_type, "gold_patch_reference": case.gold_patch_reference}
        )
        state = WorkflowState(task=task)

        # Plan + Execute
        plan = planner.generate_plan(task)
        state.plan = plan
        tool_count = 0
        for step in plan.steps:
            executor.execute_step(state, step)
            tool_count += 1

        # Single verification check (no retry on failure)
        report = verifier.verify_patch(state)
        tool_count += 3

        patch_code = state.current_patch_code or case.vulnerable_code
        if report.status == "FAIL":
            # Gated rejection: If verification failed, don't deploy
            patch_code = case.vulnerable_code

        duration = round(time.perf_counter() - start_time, 3)

        res = scorer.evaluate_case(
            case=case,
            patch_code=patch_code,
            version="V3_VerifierGate",
            retry_count=0,
            duration_seconds=duration,
            cost_usd=0.035,
            tool_calls_count=tool_count
        )
        results.append(res)

    return results


if __name__ == "__main__":
    results = run_v3_experiment()
    from evaluation.metrics import AggregateMetrics
    agg = AggregateMetrics.compute("V3_VerifierGate", results)
    print(f"V3 Verifier Gate Success Rate (RSR): {agg.remediation_success_rate}% ({agg.successful_cases}/{agg.total_cases})")
