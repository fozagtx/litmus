"""
Evaluation Reports & Evidence Generator.
Outputs structured markdown reports, JSON evidence logs, and terminal tables.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List
from rich.console import Console
from rich.table import Table
from evaluation.metrics import AggregateMetrics, CaseEvaluationResult
from evaluation.comparison import ComparativeExperimentReport


class ReportGenerator:
    def __init__(self, output_dir: str = "/Users/kaizen/Desktop/litmus/evidence"):
        self.output_dir = Path(output_dir)
        self.raw_dir = self.output_dir / "raw"
        self.proc_dir = self.output_dir / "processed"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.proc_dir.mkdir(parents=True, exist_ok=True)
        self.console = Console()

    def save_raw_results(self, version: str, results: List[CaseEvaluationResult]) -> str:
        out_file = self.raw_dir / f"results_{version}.json"
        data = [r.model_dump() for r in results]
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return str(out_file)

    def save_comparison_report(self, report: ComparativeExperimentReport) -> str:
        out_file = self.proc_dir / "comparative_experiment_report.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2)
        return str(out_file)

    def print_terminal_summary(self, report: ComparativeExperimentReport):
        table = Table(title="🔬 Micro1 Evaluation: Experimental Ladder vs Baseline")
        table.add_column("Version", style="cyan", justify="left")
        table.add_column("Success (RSR)", style="green", justify="right")
        table.add_column("Δ vs Base (Abs)", style="bold yellow", justify="right")
        table.add_column("Δ vs Base (Rel)", style="bold magenta", justify="right")
        table.add_column("Compilation", justify="right")
        table.add_column("Exploit Neut.", justify="right")
        table.add_column("Invariants", justify="right")
        table.add_column("Mean Retries", justify="right")
        table.add_column("Mean Latency", justify="right")

        for v in report.versions:
            agg = report.aggregate_metrics[v]
            delta = report.deltas_vs_baseline.get(v)
            abs_str = f"+{delta.absolute_delta_rsr}%" if delta and delta.absolute_delta_rsr > 0 else (f"{delta.absolute_delta_rsr}%" if delta else "-")
            rel_str = f"+{delta.relative_delta_rsr}%" if delta and delta.relative_delta_rsr > 0 else (f"{delta.relative_delta_rsr}%" if delta else "-")

            table.add_row(
                v,
                f"{agg.remediation_success_rate:.1f}%",
                abs_str,
                rel_str,
                f"{agg.compilation_pass_rate:.1f}%",
                f"{agg.exploit_neutralization_rate:.1f}%",
                f"{agg.invariant_preservation_rate:.1f}%",
                f"{agg.mean_retries:.1f}",
                f"{agg.mean_latency_seconds:.2f}s"
            )

        self.console.print(table)

    def generate_markdown_summary(self, report: ComparativeExperimentReport) -> str:
        md = ["# Evaluation Results Summary\n"]
        md.append("| Version | Success Rate (RSR) | Absolute Δ | Relative Δ | Compilation | Exploit Neut. | Invariants | Latency |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

        for v in report.versions:
            agg = report.aggregate_metrics[v]
            delta = report.deltas_vs_baseline.get(v)
            abs_str = f"+{delta.absolute_delta_rsr}%" if delta and delta.absolute_delta_rsr > 0 else (f"{delta.absolute_delta_rsr}%" if delta else "Baseline")
            rel_str = f"+{delta.relative_delta_rsr}%" if delta and delta.relative_delta_rsr > 0 else (f"{delta.relative_delta_rsr}%" if delta else "Baseline")

            md.append(f"| **{v}** | **{agg.remediation_success_rate:.1f}%** ({agg.successful_cases}/{agg.total_cases}) | {abs_str} | {rel_str} | {agg.compilation_pass_rate:.1f}% | {agg.exploit_neutralization_rate:.1f}% | {agg.invariant_preservation_rate:.1f}% | {agg.mean_latency_seconds:.2f}s |")

        return "\n".join(md)
