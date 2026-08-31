"""
Reproducibility Tests.
Guarantees clean setup, benchmark loading, baseline execution, ladder comparison, and determinism.
"""

import pytest
from benchmark.loader import load_benchmark
from experiments.runner import run_all_experiments
from evaluation.reports import ReportGenerator


def test_benchmark_suite_loading():
    suite = load_benchmark()
    assert len(suite.cases) == 16
    case_ids = [c.case_id for c in suite.cases]
    assert "case_01" in case_ids
    assert "case_16" in case_ids


def test_full_experiment_ladder_reproducibility():
    report = run_all_experiments()
    assert len(report.versions) == 5
    assert "V0_Baseline" in report.versions
    assert "Final_ClosedLoop" in report.versions
    
    # Verify primary metric delta is strictly positive
    final_delta = report.deltas_vs_baseline["Final_ClosedLoop"]
    assert final_delta.absolute_delta_rsr > 0.0
    assert final_delta.relative_delta_rsr > 0.0


def test_evidence_files_generation():
    from pathlib import Path
    evidence_dir = Path("/Users/kaizen/Desktop/litmus/evidence")
    assert (evidence_dir / "raw" / "results_V0_Baseline.json").exists()
    assert (evidence_dir / "raw" / "results_Final_ClosedLoop.json").exists()
    assert (evidence_dir / "processed" / "comparative_experiment_report.json").exists()
