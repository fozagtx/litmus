"""
Benchmark Case & Reference Schema.
Defines strict Pydantic schemas for standardized benchmark cases,
expected properties, exploit specifications, and gold references.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RegressionTestCase(BaseModel):
    name: str
    description: str
    function_called: str
    caller: str = "0xUser1"
    args: Dict[str, Any] = Field(default_factory=dict)
    expected_success: bool = True


class BenchmarkCase(BaseModel):
    case_id: str
    title: str
    category: str
    difficulty: str  # "Normal", "Difficult", "Edge Case", "Adversarial"
    vulnerability_type: str
    vulnerable_code: str
    vulnerability_description: str
    exploit_poc: str
    invariants: List[str] = Field(default_factory=list)
    regression_tests: List[RegressionTestCase] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    gold_patch_reference: Optional[str] = None
    baseline_failure_mode: str = ""


class BenchmarkSuite(BaseModel):
    version: str = "1.0.0"
    cases: List[BenchmarkCase] = Field(default_factory=list)

    def get_case(self, case_id: str) -> Optional[BenchmarkCase]:
        for case in self.cases:
            if case.case_id == case_id:
                return case
        return None
