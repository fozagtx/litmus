"""
Benchmark Loader & Validator.
Loads the frozen benchmark suite from JSON cases and validates schema conformance.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import List, Optional
from benchmark.schema import BenchmarkCase, BenchmarkSuite


class BenchmarkLoader:
    def __init__(self, cases_dir: Optional[str] = None):
        if cases_dir:
            self.cases_dir = Path(cases_dir)
        else:
            self.cases_dir = Path(__file__).parent / "cases"

    def load_suite(self) -> BenchmarkSuite:
        cases: List[BenchmarkCase] = []
        if not self.cases_dir.exists():
            raise FileNotFoundError(f"Cases directory not found: {self.cases_dir}")

        json_files = sorted(list(self.cases_dir.glob("*.json")))
        for f in json_files:
            try:
                with open(f, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    case = BenchmarkCase(**data)
                    cases.append(case)
            except Exception as e:
                print(f"Error loading {f.name}: {e}")

        return BenchmarkSuite(version="1.0.0", cases=cases)


def load_benchmark() -> BenchmarkSuite:
    loader = BenchmarkLoader()
    return loader.load_suite()
