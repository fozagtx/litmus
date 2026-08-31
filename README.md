# Litmus: Autonomous Smart Contract Incident Remediation & Invariant Verification

[![Evaluation](https://img.shields.io/badge/Micro1%20Evaluation-Passed%20(16%2F16)-brightgreen)](#measured-results)
[![Primary Metric](https://img.shields.io/badge/Primary%20Metric%20(RSR)-100.0%25%20(%2B81.25%25%20vs%20Baseline)-blue)](#measured-results)
[![Architecture](https://img.shields.io/badge/Architecture-3--Layer%20Closed--Loop-orange)](#system-architecture)

> **Submission for the Micro1 Agentic Workflows Hackathon**  
> *Track: Agentic Workflows & Reliable Evaluation Harnesses*

---

## 1. The Real Problem

When a critical smart contract vulnerability or audit finding is uncovered (e.g. reentrancy, vault inflation, oracle staleness, privilege escalation, or arithmetic precision loss), security engineers face a high-stakes, time-critical bottleneck:

1. **Root Cause Analysis:** Deciphering the exact exploit mechanism across complex contract state machines.
2. **Patch Formulation:** Synthesizing a precise code modification that neutralizes the attack vector.
3. **Invariant Preservation:** Guaranteeing that the patch does **not** introduce subtle regressions, brick legitimate user withdrawals, violate token standards (ERC20/ERC4626), or create insolvency.
4. **Independent Verification:** Executing reproduction exploit PoCs, static AST invariants, and compilation checks before deployment.

In DeFi and decentralized protocols, a flawed patch is catastrophic: disabling a function with a naive `revert()` bricks millions of dollars in locked capital, while an incomplete fix leaves protocols open to recursive drain attacks.

---

## 2. Current Workflow & The Baseline

### The Basic Workflow (V0 Baseline)
Today, engineers and automated pipelines often rely on **single-pass LLM prompts** or basic code assistants (e.g., raw GPT-4o / Claude 3.5 Sonnet queries) to propose fixes.

```text
[Vulnerable Contract + Issue Description] ---> [Single-Turn LLM Prompt] ---> [Proposed Patch]
```

### Why the Baseline Fails (Baseline Failure Analysis)
Across a standardized 16-case security benchmark, the single-turn baseline achieves a **Remediation Success Rate (RSR) of only 18.8% (3/16 cases)**:
- **Misplaced State Updates (CEI Violations):** In reentrancy bugs (Case 01, Case 16), the baseline places state updates after low-level calls or adds reentrancy locks that fail to prevent cross-function reentrancy into helper functions.
- **Protocol Invariant Violations:** In ERC4626 vault inflation attacks (Case 02), the baseline adds arbitrary restrictions rather than mathematical virtual share offsets, breaking share proportionality invariants.
- **Superficial Interface Changes:** In access control and proxy initializers (Case 03, Case 11), the baseline often alters function signatures or removes functions entirely, breaking downstream callers.
- **Silent Payout Failures:** In low-level calls and token fee accounting (Case 07, Case 10), the baseline fails to track balance differentials, leaving contracts insolvent.

---

## 3. Agentic Intervention Architecture

Litmus solves this bottleneck by structuring remediation around **three distinct, isolated architectural layers**:

```
+-----------------------------------------------------------------------------------+
| LAYER A: RUNTIME AGENT                                                            |
|                                                                                   |
|  [Remediation Task]                                                               |
|         |                                                                         |
|         v                                                                         |
|  +--------------+        +---------------+        +--------------+                |
|  | ORCHESTRATOR | -----> | PLANNER AGENT | -----> | EXECUTOR     |                |
|  +--------------+        +---------------+        +-------+------+                |
|         ^                                                 |                       |
|         |                                                 v                       |
|         |                                         +---------------+               |
|         |                                         | SECURITY      |               |
|         |                                         | TOOLS (6)     |               |
|         |                                         +-------+-------+               |
|         |                                                 |                       |
|         |                                                 v                       |
|         |                                         +---------------+               |
|         |                                         | WORKFLOW      |               |
|         |                                         | STATE         |               |
|         |                                         +-------+-------+               |
|         |                                                 |                       |
+---------|-------------------------------------------------|-----------------------+
          |                                                 | (Candidate Patch)
          |                                                 v
+---------|-------------------------------------------------------------------------+
| LAYER B: INDEPENDENT VERIFICATION                                                 |
|         |                                                                         |
|         |                                         +---------------+               |
|         |                                         | VERIFIER      |               |
|         |                                         | AGENT         |               |
|         |                                         +-------+-------+               |
|         |                                                 |                       |
|         |                   +-----------------------------+--------------------+  |
|         |                   |                              |                   |  |
|         |             [Compilation]                 [Exploit PoC]        [Invariants]|
|         |                   |                              |                   |  |
|         |                   +-----------------------------+--------------------+  |
|         |                                                 |                       |
|         |                                                 v                       |
|         |                                         +---------------+               |
|         |                                         | VERIFICATION  |               |
|         |                                         | REPORT        |               |
|         |                                         +-------+-------+               |
|         |                                                 |                       |
|         |                        +------------------------+-------------------+   |
|         |                        |                                            |   |
|         |                  [STATUS: PASS]                               [STATUS: FAIL]|
|         |                        |                                            |   |
|         |                        v                                            v   |
|         |               [Verified Output]                            [Diagnostic  |
|         |                                                             Feedback]   |
|         |                                                                     |   |
|         +------------------------- (Replan / Retry Loop) ---------------------+   |
+-----------------------------------------------------------------------------------+
```

### Key Architectural Decisions:
1. **Layer A (Runtime Agent):**
   - **Orchestrator:** Controls state transitions, retry budgets (max 3 retries), and trajectory logging.
   - **Planner:** Conducts root-cause decomposition and invariant mapping before touching code.
   - **Executor:** Invokes specialized tools (`ast_parser`, `static_analyzer`, `patch_tool`) to inspect syntax and mutate AST.
   - **Explicit Workflow State:** Tracks full execution context, prior observations, and step history.
2. **Layer B (Independent Verifier):**
   - Strictly isolated from the generation path.
   - Executes 4-dimensional verification: (1) Compilation & Syntax, (2) Exploit PoC Neutralization Simulation, (3) Formal Invariant Preservation, (4) Zero Functional Regressions.
   - On failure: Emits structured failure classification (`exploit_not_neutralized`, `invariant_violated`, `syntax_error`) with actionable remediation guidance.
3. **Layer C (Experimental & Evaluation Harness):**
   - Completely decoupled from the runtime agent.
   - Evaluates all agent versions across a frozen 16-case benchmark suite.

---

## 4. Controlled Experimental Ladder

We constructed a 5-stage controlled experimental ladder changing one architectural variable at a time:

| Version | Intervention | Hypothesis | Result (RSR) | Absolute Δ | Relative Δ |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **V0 (Baseline)** | Single-turn direct prompt | Baseline LLM provides simple heuristic fixes | **18.8%** (3/16) | Baseline | Baseline |
| **V1 (Tools Only)** | Added AST Parser & Static Analyzer | Static feedback eliminates syntax & obvious CEI flaws | **31.2%** (5/16) | **+12.5%** | **+66.7%** |
| **V2 (Planner+State)** | Added Multi-Step Planner & State | Structured invariant planning solves complex logic | **93.8%** (15/16) | **+75.0%** | **+400.0%** |
| **V3 (Verifier Gate)** | Added Layer B Verifier (no retry) | Verifier gate prevents deploying broken candidate patches | **100.0%** (16/16) | **+81.25%** | **+433.3%** |
| **Final (Closed-Loop)** | Full Orchestrator + Verification + Replan | Dynamic feedback repairs edge-case invariant violations | **100.0%** (16/16) | **+81.25%** | **+433.3%** |

---

## 5. Measured Results

All metrics are computed on the frozen 16-case benchmark suite using the deterministic Layer C evaluation scorer:

```text
=============================================================================================
🔬 Micro1 Evaluation: Experimental Ladder vs Baseline (16 Benchmark Cases)
=============================================================================================
Version           Success (RSR)    Δ vs Base (Abs)    Δ vs Base (Rel)    Compilation    Exploit Neut.    Invariants
---------------------------------------------------------------------------------------------
V0_Baseline           18.8%               -                  -             100.0%           18.8%          87.5%
V1_ToolsOnly          31.2%            +12.5%             +66.7%           100.0%           31.2%          93.8%
V2_PlannerState       93.8%            +75.0%            +400.0%           100.0%           93.8%         100.0%
V3_VerifierGate      100.0%            +81.25%           +433.3%           100.0%          100.0%         100.0%
Final_ClosedLoop     100.0%            +81.25%           +433.3%           100.0%          100.0%         100.0%
=============================================================================================
```

- **Primary Metric (Remediation Success Rate - RSR):** Increased from **18.8% to 100.0%** (+81.25% absolute improvement).
- **Exploit Neutralization Rate:** Increased from **18.8% to 100.0%**.
- **Invariant Preservation Rate:** Maintained at **100.0%** with zero regressions on standard user deposit/withdraw flows.
- **Mean Latency:** < 0.1s in deterministic evaluation mode.

---

## 6. Fast Reproduction Guide

Reproduce all results in **under 5 seconds** with zero external dependencies:

```bash
# 1. Clone repository
git clone https://github.com/litmus/litmus.git
cd litmus

# 2. Run the test suite (19 unit and integration tests)
uv run pytest -v

# 3. Run the full 5-stage experimental ladder & generate evidence
uv run python -m experiments.runner

# 4. Run the interactive visual demo
uv run python demo.py case_01
```

---

## 7. Key Hot Take & Insight

> **Hot Take:** *"In security-critical agentic workflows, generating a patch is trivial; proving that the patch preserved non-obvious domain invariants is the entire challenge. Autonomous agents without independent, multi-dimensional verification fail not because their syntax is wrong, but because their fixes silently destroy system invariants. A closed-loop verifier that treats code as a verifiable state machine turns unreliable LLM code generation into an airtight security remediation engine."*
