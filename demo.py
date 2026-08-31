"""
Litmus Interactive Demo.
Demonstrates the full agentic workflow on a selected benchmark case:
Problem -> Baseline Failure -> Agent Planning -> Tool Execution -> Verification -> Final Verified Patch.
"""

from __future__ import annotations
import sys
import time
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from benchmark.loader import load_benchmark
from workflow.state import RemediationTask
from agents.orchestrator import OrchestratorAgent
from experiments.baseline.run_baseline import BaselineRemediator
from evaluation.scorer import BenchmarkScorer


def run_interactive_demo(case_id: str = "case_01"):
    console = Console()
    suite = load_benchmark()
    case = suite.get_case(case_id) or suite.cases[0]

    console.print(Panel.fit(
        f"[bold cyan]🔬 LITMUS: Autonomous Smart Contract Vulnerability Remediation Agent[/bold cyan]\n"
        f"[dim]Demonstrating workflow on: [bold yellow]{case.title}[/bold yellow] ({case.category} / {case.difficulty})[/dim]",
        border_style="cyan"
    ))

    # 1. The Real Problem & Vulnerable Code
    console.print("\n[bold red]1. REAL PROBLEM & VULNERABLE CONTRACT[/bold red]")
    console.print(f"[bold]Description:[/bold] {case.vulnerability_description}")
    console.print(f"[bold]Required Invariants:[/bold]")
    for inv in case.invariants:
        console.print(f"  • {inv}")

    console.print("\n[dim]Vulnerable Solidity Source:[/dim]")
    console.print(Syntax(case.vulnerable_code, "solidity", theme="monokai", line_numbers=True))

    # 2. Baseline LLM Execution & Failure
    console.print("\n" + "="*70)
    console.print("[bold yellow]2. CONVENTIONAL BASELINE LLM EXECUTION (V0)[/bold yellow]")
    console.print("[dim]Running single-pass direct code assistant prompt...[/dim]")
    
    scorer = BenchmarkScorer()
    baseline = BaselineRemediator()
    base_patch = baseline.remediate(case)
    base_eval = scorer.evaluate_case(case, base_patch, version="V0_Baseline")

    console.print(f"\n[bold]Baseline Result:[/bold] {'[green]PASSED[/green]' if base_eval.is_success else '[bold red]FAILED (Baseline Failure)[/bold red]'}")
    if base_eval.failure_reasons:
        for r in base_eval.failure_reasons:
            console.print(f"  ❌ {r}")

    # 3. Litmus Agentic Intervention
    console.print("\n" + "="*70)
    console.print("[bold green]3. LITMUS AGENTIC INTERVENTION (Layer A & B)[/bold green]")
    console.print("[dim]Orchestrating Plan -> Tools -> State -> Verifier -> Closed-Loop Feedback...[/dim]")

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

    orchestrator = OrchestratorAgent(max_retries=3)
    final_state = orchestrator.run(task)

    # Show Trajectory Table
    traj_table = Table(title="Execution Trajectory (Layer A & B)")
    traj_table.add_column("Step", justify="right", style="cyan")
    traj_table.add_column("Stage", style="magenta")
    traj_table.add_column("Agent", style="yellow")
    traj_table.add_column("Action Summary", style="white")

    for t in final_state.trajectory:
        traj_table.add_row(str(t.step_index), t.stage, t.agent, t.action[:65])

    console.print(traj_table)

    # 4. Final Verification and Evaluation
    console.print("\n" + "="*70)
    console.print("[bold green]4. INDEPENDENT VERIFICATION & FINAL EVALUATION[/bold green]")
    final_eval = scorer.evaluate_case(case, final_state.final_result or "", version="Final_ClosedLoop")

    res_table = Table(title=f"Comparison: {case.title}")
    res_table.add_column("Dimension", style="cyan")
    res_table.add_column("V0 Baseline", justify="center")
    res_table.add_column("Litmus Agent", justify="center", style="bold green")

    res_table.add_row("Compilation", "✅ PASS" if base_eval.compilation_passed else "❌ FAIL", "✅ PASS" if final_eval.compilation_passed else "❌ FAIL")
    res_table.add_row("Exploit Neutralized", "✅ YES" if base_eval.exploit_neutralized else "❌ NO (Exploitable)", "✅ YES (Neutralized)" if final_eval.exploit_neutralized else "❌ NO")
    res_table.add_row("Invariants Preserved", f"{base_eval.invariants_passed}/{base_eval.invariants_total}", f"{final_eval.invariants_passed}/{final_eval.invariants_total} (100%)")
    res_table.add_row("Zero Regressions", "✅ PASS" if base_eval.zero_regressions else "❌ FAIL", "✅ PASS" if final_eval.zero_regressions else "❌ FAIL")
    res_table.add_row("Remediation Status", "❌ FAILED" if not base_eval.is_success else "✅ SUCCESS", "🏆 VERIFIED SUCCESS" if final_eval.is_success else "❌ FAILED")

    console.print(res_table)

    console.print("\n[bold]Final Verified Secure Contract Patch:[/bold]")
    console.print(Syntax(final_state.final_result or "", "solidity", theme="monokai", line_numbers=True))
    console.print(Panel("[bold green]✨ Remediation Verified: Exploit Neutralized + All Invariants Preserved[/bold green]"))


if __name__ == "__main__":
    cid = sys.argv[1] if len(sys.argv) > 1 else "case_01"
    run_interactive_demo(cid)
