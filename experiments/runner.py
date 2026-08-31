"""
Unified Experiment Runner & Master Harness.
Executes the full experimental ladder (V0 Baseline, V1 Tools, V2 Planner, V3 Verifier, Final),
generates raw evidence files, comparative JSON reports, and prints the summary table.
"""

from __future__ import annotations
import os
import json
from typing import Dict, List
from evaluation.metrics import CaseEvaluationResult, AggregateMetrics
from evaluation.comparison import ComparativeExperimentReport
from evaluation.reports import ReportGenerator
from experiments.baseline.run_baseline import run_baseline_experiment
from experiments.v1_tools.run_v1 import run_v1_experiment
from experiments.v2_planner.run_v2 import run_v2_experiment
from experiments.v3_verifier.run_v3 import run_v3_experiment
from experiments.final.run_final import run_final_experiment


def run_all_experiments() -> ComparativeExperimentReport:
    report_gen = ReportGenerator()
    runs: Dict[str, List[CaseEvaluationResult]] = {}

    print("==================================================")
    print("🚀 RUNNING LITMUS EXPERIMENTAL LADDER (16 BENCHMARK CASES)")
    print("==================================================")

    # 1. V0 Baseline
    print("\n[1/5] Running V0 Baseline (Single-turn LLM)...")
    v0_results = run_baseline_experiment()
    runs["V0_Baseline"] = v0_results
    report_gen.save_raw_results("V0_Baseline", v0_results)

    # 2. V1 Tools Only
    print("\n[2/5] Running V1 Tools-Only (Executor + AST/Static Analysis)...")
    v1_results = run_v1_experiment()
    runs["V1_ToolsOnly"] = v1_results
    report_gen.save_raw_results("V1_ToolsOnly", v1_results)

    # 3. V2 Planner + State
    print("\n[3/5] Running V2 Planner+State (Structured Plan + State Tracking)...")
    v2_results = run_v2_experiment()
    runs["V2_PlannerState"] = v2_results
    report_gen.save_raw_results("V2_PlannerState", v2_results)

    # 4. V3 Verifier Gate
    print("\n[4/5] Running V3 Verifier Gate (Layer B Verifier without Retry)...")
    v3_results = run_v3_experiment()
    runs["V3_VerifierGate"] = v3_results
    report_gen.save_raw_results("V3_VerifierGate", v3_results)

    # 5. Final Closed-Loop
    print("\n[5/5] Running Final System (Closed-Loop Orchestrator + Verification + Replan/Retry)...")
    final_results = run_final_experiment()
    runs["Final_ClosedLoop"] = final_results
    report_gen.save_raw_results("Final_ClosedLoop", final_results)

    # Generate Comparative Report
    print("\n==================================================")
    print("📊 COMPUTING DELTAS AND COMPARATIVE METRICS")
    print("==================================================")
    comparison_report = ComparativeExperimentReport.compare(
        baseline_version="V0_Baseline",
        runs=runs
    )

    report_gen.save_comparison_report(comparison_report)
    report_gen.print_terminal_summary(comparison_report)

    return comparison_report


if __name__ == "__main__":
    run_all_experiments()
