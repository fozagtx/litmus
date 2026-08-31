"""
Evaluation Runner CLI.
Runs evaluation on benchmark cases and outputs formatted metrics.
"""

from __future__ import annotations
import sys
from experiments.runner import run_all_experiments


def main():
    print("🔬 Micro1 Agentic Workflows Hackathon - Evaluation Suite")
    report = run_all_experiments()
    print("\n✅ Evaluation successfully completed. Evidence saved to evidence/raw/ and evidence/processed/.")


if __name__ == "__main__":
    main()
