# Litmus

**Autonomous smart contract incident remediation and invariant verification.**

[![Evaluation](https://img.shields.io/badge/Micro1%20Evaluation-Passed%20(16%2F16)-brightgreen)](#measured-results)
[![Primary Metric](https://img.shields.io/badge/Primary%20Metric%20(RSR)-100.0%25%20(+81.25%25%20vs%20Baseline)-blue)](#measured-results)
[![Architecture](https://img.shields.io/badge/Architecture-3--Layer%20Closed--Loop-orange)](#system-architecture)

Litmus takes an audit finding and returns a verified patch: compiled, exploit-killed, invariants intact, legitimate flows still working.

---
The first five months of 2026 made the cost of delay visible. In January, attackers drained over $75M across multiple protocols, including a $26M integer overflow on Truebit and a $40M private key compromise on Step Finance. February added about $23.5M from oracle manipulation and bridge compromises, including YieldBlox and IoTeX. March added about $52M across 20+ incidents: Solv Protocol ($2.7M, double-mint), Venus Protocol ($3.7M, flash loan), dTRINITY dLEND (logic error), and Resolv Labs (private key, 80M unbacked mint). By the end of Q1, losses reached $168.6M across 34 protocols. May accelerated again: $68.3M across 60 incidents, including TrustedVolumes ($6.7M, proxy bug) and Verus Bridge ($11.58M, validation gap).

An audit can name a critical vulnerability , A researcher can ship a proof of concept , The team can agree on what must change. But someone has to patch the contract and prove the patch works before an attacker uses the same finding.

That work spans more than a one-line edit.
After the finding, the remaining path is:

```text
Audit finding
  → root cause
  → safe patch design
  → implementation
  → compile
  → reproduce the exploit
  → prove invariants still hold
  → check functional regressions
  → deploy
```

A slow patch leaves the hole open. An aggressive patch can break withdrawals, accounting, ERC assumptions, or introduce a new vulnerability. Litmus targets the interval between a known finding and a verified fix.

---

## What Litmus does

Litmus runs remediation as a closed loop.

```text
Audit finding
  → root-cause analysis
  → invariant mapping
  → patch generation
  → compilation
  → exploit reproduction
  → invariant verification
      PASS → verified patch
      FAIL → diagnostic feedback → replan → patch again
```

The run ends when the candidate survives independent verification.

---

## Why single-turn LLM remediation fails

The naive path is one prompt:

```text
[Vulnerable contract + audit finding]
  → single-turn LLM
  → proposed patch
```

On a frozen 16-case security benchmark, that baseline reached **18.8% Remediation Success Rate (3/16)**.

The usual failure is semantic. Smart contract bugs sit in state, accounting, permissions, and protocol invariants.

- **Reentrancy.** A model may move a state update or add a guard and miss cross-function paths.
- **Vault inflation.** A model may block the exploit and still break ERC-4626 share-price and proportionality invariants.
- **Access control.** A model may delete or reshape a function instead of keeping the public interface and fixing authorization.
- **Accounting.** A model may patch one transfer path and leave balance differentials that insolvent the protocol.

A patch can compile, look plausible, pass a shallow check, and remain exploitable.

---

## System architecture

Three isolated layers.

### Layer A: runtime remediation agent

Produces candidate patches.

- **Orchestrator.** Owns workflow, state transitions, retry budget, and trajectory logs.
- **Planner.** Decomposes the finding before any edit: root cause, attack mechanism, affected state transitions, relevant invariants, patch constraints.
- **Executor.** Inspects and edits the contract with `ast_parser`, `static_analyzer`, and `patch_tool`.
- **Explicit workflow state.** Keeps execution context, observations, and step history across attempts.

### Layer B: independent verification

The verifier sits outside the generation path. A process that wrote the patch does not also declare it correct.

Four checks:

1. **Compilation and syntax.** Does the patched contract compile?
2. **Exploit neutralization.** Does the original PoC still succeed?
3. **Invariant preservation.** Do the mathematical and protocol properties still hold?
4. **Functional regression.** Do legitimate deposits, withdrawals, transfers, and other expected paths still work?

Structured diagnostics include `exploit_not_neutralized`, `invariant_violated`, `syntax_error`, and `functional_regression`. Failed candidates stay undeployed. Diagnostics go back to the agent.

### Layer C: evaluation harness

Separated from the runtime agent. Scores each architecture against the same frozen 16-case benchmark so each intervention can be measured.

---

## Closed-loop flow

```text
┌───────────────────────┐
│ AUDIT FINDING         │
└───────────┬───────────┘
            ▼
┌───────────────────────┐
│ ORCHESTRATOR          │
└───────────┬───────────┘
            ▼
┌───────────────────────┐
│ PLANNER               │
│ root cause            │
│ attack path           │
│ invariants            │
└───────────┬───────────┘
            ▼
┌───────────────────────┐
│ EXECUTOR              │
│ AST parser            │
│ static analyzer       │
│ patch tool            │
└───────────┬───────────┘
            ▼
┌─────────────┐
│ PATCH       │
└──────┬──────┘
       ▼
┌────────────────────────────────┐
│ INDEPENDENT VERIFIER           │
│ compilation · exploit PoC      │
│ invariants · functional checks │
└───────────────┬────────────────┘
       ┌────────┴────────┐
     PASS              FAIL
       ▼                 ▼
┌──────────────┐  ┌──────────────┐
│ VERIFIED     │  │ DIAGNOSTIC   │
│ PATCH        │  │ FEEDBACK     │
└──────────────┘  └──────┬───────┘
                         ▼
                  ┌──────────┐
                  │ REPLAN   │
                  └────┬─────┘
                       └── retry
```

Failed attempts feed diagnostics back into the planner. The next patch is a response to those diagnostics.

---

## Experimental results

One variable changed at a time on the same 16-case benchmark.

| Version | Intervention | RSR |
| --- | --- | ---: |
| V0 Baseline | Single-turn direct prompt | **18.8%** |
| V1 Tools only | AST parser + static analyzer | **31.2%** |
| V2 Planner + state | Multi-step planner + explicit state | **93.8%** |
| V3 Verifier gate | Independent verification | **100.0%** |
| Final closed loop | Verification + replanning | **100.0%** |

```text
18.8% → 31.2% → 93.8% → 100.0%
```

Final system: **100% RSR (16/16)** against **18.8% (3/16)** baseline. Absolute gain: **81.25 percentage points**. Relative gain: **433.3%**.

Ladder:

- Tools alone: 18.8% → 31.2%.
- Planning and explicit state: → 93.8%. Largest jump.
- Independent verifier: → 100%.
- Closed-loop replan: verifier feedback drives the next attempt.

### Measured results

All metrics from the frozen 16-case suite and the deterministic Layer C scorer.

```text
=============================================================================================
Micro1 Evaluation: Experimental Ladder vs Baseline
=============================================================================================
Version              RSR     Exploit Neutralization    Invariants
---------------------------------------------------------------------------------------------
V0 Baseline          18.8%   18.8%                     87.5%
V1 Tools Only        31.2%   31.2%                     93.8%
V2 Planner+State     93.8%   93.8%                     100.0%
V3 Verifier          100.0%  100.0%                    100.0%
Final ClosedLoop     100.0%  100.0%                    100.0%
=============================================================================================
```

- **Remediation success rate:** 18.8% → 100.0%
- **Exploit neutralization:** 18.8% → 100.0%
- **Invariant preservation:** 100.0% in the final evaluation, with no regressions on the tested standard deposit/withdraw flows
- **Deterministic evaluation latency:** < 0.1 seconds

Patch generation without structured reasoning and independent verification stayed unreliable on this suite.

---

## Configuration and integration

Litmus is a library. Call it from scripts or from a larger agent workflow (Cursor, Continue, Aider, LangGraph, AutoGen, custom orchestrators). Configuration is environment variables, `litmus.toml`, and a Python call. There is no standalone `litmus` CLI.

### Environment (`.env`)

```env
# LLM backend
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
LITMUS_MODEL=gpt-4o

# Workflow limits
LITMUS_MAX_RETRIES=3
LITMUS_VERIFIER_TIMEOUT=30

# Tool paths
SOLC_PATH=/usr/bin/solc
FORGE_PATH=/usr/bin/forge
```

### Project config (`litmus.toml`)

```toml
[llm]
provider = "openai"
model = "gpt-4o"
temperature = 0.2

[workflow]
max_retries = 3
verifier_strictness = "high"  # "standard" | "high" | "paranoid"

[invariants]
custom_checks = ["./checks/erc4626.py", "./checks/access_control.py"]
```

### Python API

```python
from litmus import run_remediation

result = run_remediation(
    contract_path="contracts/Vault.sol",
    finding_text="Reentrancy vulnerability in withdraw()",
    config={
        "model": "gpt-4o",
        "max_retries": 3,
        "verifier_strictness": "high",
    },
)

print(result["status"])
print(result["patch_path"])
print(result["verification"])
```

`result` is a dict. Pass it to another agent or write it to an audit log.

### Subprocess from another orchestrator

```python
import json
import subprocess

def run_litmus(contract_path: str, finding_text: str) -> dict:
    completed = subprocess.run(
        [
            "python",
            "-c",
            (
                "from litmus import run_remediation; "
                "import json, sys; "
                "print(json.dumps(run_remediation(sys.argv[1], sys.argv[2])))"
            ),
            contract_path,
            finding_text,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)
```

### IDE hooks (Cursor / Continue)

Point a custom command at a small wrapper script that calls `run_remediation` with the active file and the selected finding text.

### Custom prompts

Override templates by placing files in `./prompts/`:

- `planner_system.txt`
- `executor_patch.txt`
- `verifier_rules.txt`

---

## Why this matters

After a critical finding, the team still has to ship a fix that leaves the protocol intact.

Too slow and the hole stays open. Too fast and the patch becomes the next incident.

Litmus covers the window after the audit and before deploy:

```text
Understand the finding
  → reason about the attack
  → map invariants
  → generate a patch
  → test the patch
  → diagnose failure
  → replan
  → verify again
  → return a verified candidate
```

Auditors still own discovery. Litmus shortens the interval between a known finding and a patch you can defend.

---

## Getting started

Reproduce the experimental ladder with no external service dependencies for the harness itself.

```bash
git clone https://github.com/fozagtx/litmus.git
cd litmus

uv sync
cp .env.example .env

uv run pytest -v
uv run python -m experiments.runner
uv run python demo.py case_01
```

