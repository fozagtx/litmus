"""
Evaluation Metrics Architecture (Layer C).
Defines primary and secondary evaluation metrics for smart contract vulnerability remediation.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class CaseEvaluationResult(BaseModel):
    case_id: str
    version: str
    patch_code: str
    compilation_passed: bool
    exploit_neutralized: bool
    invariants_passed: int
    invariants_total: int
    regressions_passed: int
    regressions_total: int
    all_invariants_passed: bool
    zero_regressions: bool
    is_success: bool  # Primary Metric: True iff all 4 dimensions pass
    failure_reasons: List[str] = Field(default_factory=list)
    retry_count: int = 0
    duration_seconds: float = 0.0
    cost_usd: float = 0.0
    tool_calls_count: int = 0


class AggregateMetrics(BaseModel):
    version: str
    total_cases: int
    successful_cases: int
    # Primary Metric
    remediation_success_rate: float  # Percentage [0.0 - 100.0]
    # Secondary Metrics
    compilation_pass_rate: float
    exploit_neutralization_rate: float
    invariant_preservation_rate: float
    regression_freedom_rate: float
    mean_latency_seconds: float
    mean_retries: float
    mean_tool_calls: float
    total_cost_usd: float

    @classmethod
    def compute(cls, version: str, results: List[CaseEvaluationResult]) -> AggregateMetrics:
        n = len(results)
        if n == 0:
            return cls(
                version=version,
                total_cases=0,
                successful_cases=0,
                remediation_success_rate=0.0,
                compilation_pass_rate=0.0,
                exploit_neutralization_rate=0.0,
                invariant_preservation_rate=0.0,
                regression_freedom_rate=0.0,
                mean_latency_seconds=0.0,
                mean_retries=0.0,
                mean_tool_calls=0.0,
                total_cost_usd=0.0,
            )

        successes = sum(1 for r in results if r.is_success)
        comp_passes = sum(1 for r in results if r.compilation_passed)
        exploit_neuts = sum(1 for r in results if r.exploit_neutralized)
        inv_passes = sum(1 for r in results if r.all_invariants_passed)
        reg_passes = sum(1 for r in results if r.zero_regressions)
        
        total_time = sum(r.duration_seconds for r in results)
        total_retries = sum(r.retry_count for r in results)
        total_tools = sum(r.tool_calls_count for r in results)
        total_cost = sum(r.cost_usd for r in results)

        return cls(
            version=version,
            total_cases=n,
            successful_cases=successes,
            remediation_success_rate=round((successes / n) * 100.0, 2),
            compilation_pass_rate=round((comp_passes / n) * 100.0, 2),
            exploit_neutralization_rate=round((exploit_neuts / n) * 100.0, 2),
            invariant_preservation_rate=round((inv_passes / n) * 100.0, 2),
            regression_freedom_rate=round((reg_passes / n) * 100.0, 2),
            mean_latency_seconds=round(total_time / n, 3),
            mean_retries=round(total_retries / n, 2),
            mean_tool_calls=round(total_tools / n, 2),
            total_cost_usd=round(total_cost, 4),
        )
