"""
Comparative Evaluation Engine (Layer C).
Computes absolute and relative deltas across versions (V0 Baseline, V1 Tools, V2 Planner, V3 Verifier, Final)
and generates standardized comparison summaries.
"""

from __future__ import annotations
from typing import Dict, List, Any
from pydantic import BaseModel
from evaluation.metrics import AggregateMetrics, CaseEvaluationResult


class VersionDelta(BaseModel):
    baseline_version: str
    target_version: str
    absolute_delta_rsr: float  # Percentage point change
    relative_delta_rsr: float  # Percentage change
    latency_delta_seconds: float
    cost_delta_usd: float
    compilation_delta: float
    exploit_neutralization_delta: float
    invariant_delta: float


class ComparativeExperimentReport(BaseModel):
    versions: List[str]
    aggregate_metrics: Dict[str, AggregateMetrics]
    deltas_vs_baseline: Dict[str, VersionDelta]

    @classmethod
    def compare(cls, baseline_version: str, runs: Dict[str, List[CaseEvaluationResult]]) -> ComparativeExperimentReport:
        aggs = {v: AggregateMetrics.compute(v, res) for v, res in runs.items()}
        base_agg = aggs.get(baseline_version)
        deltas = {}

        if base_agg:
            base_rsr = base_agg.remediation_success_rate
            for v, agg in aggs.items():
                if v == baseline_version:
                    continue
                abs_delta = round(agg.remediation_success_rate - base_rsr, 2)
                rel_delta = round(((agg.remediation_success_rate - base_rsr) / max(base_rsr, 0.01)) * 100.0, 2)
                deltas[v] = VersionDelta(
                    baseline_version=baseline_version,
                    target_version=v,
                    absolute_delta_rsr=abs_delta,
                    relative_delta_rsr=rel_delta,
                    latency_delta_seconds=round(agg.mean_latency_seconds - base_agg.mean_latency_seconds, 3),
                    cost_delta_usd=round(agg.total_cost_usd - base_agg.total_cost_usd, 4),
                    compilation_delta=round(agg.compilation_pass_rate - base_agg.compilation_pass_rate, 2),
                    exploit_neutralization_delta=round(agg.exploit_neutralization_rate - base_agg.exploit_neutralization_rate, 2),
                    invariant_delta=round(agg.invariant_preservation_rate - base_agg.invariant_preservation_rate, 2),
                )

        return cls(
            versions=list(runs.keys()),
            aggregate_metrics=aggs,
            deltas_vs_baseline=deltas
        )
