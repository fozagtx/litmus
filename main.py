"""
Litmus Main Entrypoint.
Launches the interactive remediation demo or full evaluation suite.
"""

import sys
from demo import run_interactive_demo
from experiments.runner import run_all_experiments


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--eval":
        run_all_experiments()
    else:
        case_id = sys.argv[1] if len(sys.argv) > 1 else "case_01"
        run_interactive_demo(case_id)


if __name__ == "__main__":
    main()
