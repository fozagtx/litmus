You're absolutely right. I haven't added that yet.

Here is the **fully updated README**, now with a dedicated **"Configuration & Agentic Tooling Integration"** section. This explains exactly how to configure Litmus to work with agentic coding tools (like Cursor, Continue, Aider, or custom multi-agent frameworks) and how to customize its runtime behavior.

---

```markdown
# Litmus

**Autonomous Smart Contract Incident Remediation & Invariant Verification**

[![Evaluation](https://img.shields.io/badge/Micro1%20Evaluation-Passed%20\(16%2F16\)-brightgreen)](#measured-results)
[![Primary Metric](https://img.shields.io/badge/Primary%20Metric%20\(RSR\)-100.0%25%20\(%2B81.25%25%20vs%20Baseline\)-blue)](#measured-results)
[![Architecture](https://img.shields.io/badge/Architecture-3--Layer%20Closed--Loop-orange)](#system-architecture)

---

## The Problem

Smart contract security has a painful gap.

An audit can identify a critical vulnerability. A security researcher can produce a proof of concept. An engineering team can understand exactly what needs to change.

But then comes the dangerous part:

**Someone has to actually fix the code—and prove that the fix works—before an attacker finds the same flaw.**

And that remediation process is rarely a one-line change.

The first five months of 2026 proved this is not a theoretical concern. Attackers have been systematically dismantling protocols through a diverse set of vectors, from integer overflows to private key leaks.

---

## 2026 Incident Timeline

Below is a compiled series of major DeFi exploits from January to May 2026, demonstrating the breadth and frequency of attacks that demand rapid, verified remediation.

### January 2026
A brutal start to the year, with over **$75 million** lost across multiple protocols.

- **Truebit** — **$26M** lost due to an **integer overflow** in a 2021 contract.
- **Step Finance** — **$40M** stolen via a **private key compromise** (largest of the quarter).
- **YO Protocol** — **$3.7M** drained from a slippage-related misconfiguration.
- **MakinaFi** — **$4.2M** exploited from the DUSD/USDC Curve pool.
- **Aperture Finance & 0xswapnet** — Hit by a series of linked attacks.

### February 2026
Attackers shifted focus to cross-chain infrastructure and oracle manipulation, totaling **~$23.5M**.

- **YieldBlox DAO** — **$10M+** lost to **oracle manipulation** (USTRY price artificially inflated 100x).
- **IoTeX (ioTube)** — **$4.4M** drained via another **private key compromise** on Ethereum.
- **CrossCurve** — **$2.8M** stolen through validation bugs that spoofed bridge messages.

### March 2026
A surge in sophisticated flash-loan and logic flaws resulted in **~$52M** in losses across 20+ incidents.

- **Solv Protocol** — **$2.7M** lost to a **double-mint vulnerability** in BRO vaults.
- **Venus Protocol** — **$3.7M** exploited via a complex **flash-loan + price manipulation** attack.
- **dTRINITY dLEND** — Hit by a flash-loan abuse combined with faulty repayment accounting.
- **Resolv Labs** — Private key exploit allowed the minting of 80M unbacked stablecoins.

### May 2026
The pace accelerated again, with **$68.3 million** lost across **60 incidents**.

- **TrustedVolumes** — **$6.7M** exploited via a custom RFQ swap proxy bug.
- **Verus Bridge** — **$11.58M** drained due to a validation gap that failed to verify cross-chain asset backing.

### Summary of Losses

| Period      | Total Losses | Notable Attack Vectors                           |
| ----------- | ------------ | ------------------------------------------------ |
| **January** | ~$75M+       | Integer overflow, Private key, Slippage          |
| **February**| ~$23.5M      | Oracle manipulation, Private key, Bridge bugs    |
| **March**   | ~$52M        | Flash loans, Double-mint, Logic flaws            |
| **May**     | ~$68.3M      | RFQ proxy bugs, Bridge validation gaps           |
| **Q1 Total**| **$168.6M**  | (34 distinct protocols affected)                 |

---

## The Remediation Gap

These incidents illustrate a broader problem: **smart contract security does not end when an auditor identifies a vulnerability.**

The team still has to move from:

```text
Audit Finding
     ↓
Understand the Root Cause
     ↓
Design a Safe Patch
     ↓
Implement the Patch
     ↓
Compile
     ↓
Reproduce the Exploit
     ↓
Prove the Invariants Still Hold
     ↓
Verify No Functional Regressions
     ↓
Deploy
```

Every step takes engineering time. And teams are under pressure.

A patch that is too slow leaves a vulnerability exposed.  
A patch that is too aggressive can break withdrawals, invalidate accounting assumptions, violate ERC standards, or introduce an entirely new vulnerability.

So the real bottleneck is not simply **finding vulnerabilities**.

It is:

> **Closing the gap between discovering a vulnerability and confidently deploying a verified fix.**

Litmus is built to close that gap.

---

## What Litmus Does

Litmus turns smart contract remediation from a manual, single-pass coding task into a **closed-loop security workflow**.

Instead of asking an LLM:

```text
"Here is the vulnerable contract. Fix it."
```

Litmus creates a remediation loop:

```text
Audit Finding
      ↓
Root-Cause Analysis
      ↓
Invariant Mapping
      ↓
Patch Generation
      ↓
Compilation
      ↓
Exploit Reproduction
      ↓
Invariant Verification
      ↓
PASS ───────────────→ Verified Patch
      │
      └── FAIL
            ↓
      Diagnostic Feedback
            ↓
          Replan
            ↓
        Patch Again
```

The agent does not stop when it generates code.

**It stops when the code survives independent verification.**

---

## Why Existing LLM-Based Remediation Falls Short

The simplest approach is a single-turn prompt:

```text
[Vulnerable Contract + Audit Finding]
              ↓
        Single-Turn LLM
              ↓
        Proposed Patch
```

This looks efficient. It isn't.

Across our standardized 16-case security benchmark, this baseline achieved only **18.8% Remediation Success Rate (3/16 cases)**.

The problem is not primarily syntax. The problem is that smart contract vulnerabilities are tied to **state, accounting, permissions, and protocol invariants**.

- **Reentrancy**: A model may move state updates or add a reentrancy guard without understanding cross-function execution paths.
- **Vault Inflation**: A model may add restrictions that appear to stop the exploit while breaking ERC4626 share-price and proportionality invariants.
- **Access Control**: A model may remove or modify a function rather than preserving the contract's public interface while fixing authorization.
- **Accounting**: A model may patch a transfer path without correctly accounting for balance differentials, leaving the protocol insolvent.

A patch can therefore:

```text
Compile successfully
       ↓
Look reasonable
       ↓
Pass superficial checks
       ↓
Still be exploitable
```

That is the problem Litmus targets.

---

## System Architecture

Litmus introduces three isolated layers.

### Layer A — Runtime Remediation Agent

The Runtime Agent is responsible for understanding the vulnerability and producing candidate patches.

- **Orchestrator**: Controls the remediation workflow, state transitions, retry budget, and trajectory logging.
- **Planner**: Decomposes the vulnerability before modifying code. It identifies root cause, attack mechanism, affected state transitions, relevant protocol invariants, and required patch constraints.
- **Executor**: Uses specialized security tools to inspect and modify the contract, including `ast_parser`, `static_analyzer`, and `patch_tool`.
- **Explicit Workflow State**: The agent maintains execution context, previous observations, and step history instead of treating every attempt as an isolated prompt.

### Layer B — Independent Verification

The verifier is **isolated from the generation path**. The same process that proposes a patch should not be the only process deciding whether that patch is correct.

The verifier evaluates the candidate across four dimensions:

1. **Compilation & Syntax**: Does the patched contract actually compile?
2. **Exploit Neutralization**: Can the original exploit proof of concept still succeed?
3. **Invariant Preservation**: Does the patch preserve the mathematical and protocol properties the contract depends on?
4. **Functional Regression**: Does the fix break legitimate functionality such as normal deposits, withdrawals, transfers, or other expected contract behavior?

The verifier produces structured diagnostics such as:

```text
exploit_not_neutralized
invariant_violated
syntax_error
functional_regression
```

A failed candidate is not deployed. Its diagnostic feedback is returned to the remediation agent.

### Layer C — Evaluation Harness

The evaluation layer is completely separated from the runtime agent. It evaluates each architecture against a frozen **16-case security benchmark**, allowing us to measure exactly which architectural intervention improves remediation performance.

---

## Configuration & Agentic Tooling Integration

Litmus is built as a standalone agentic workflow, but it is designed to be **dropped into larger agentic ecosystems** (Cursor, Continue, Aider, LangGraph, AutoGen, or custom multi-agent systems).

### Environment Configuration

Configure the runtime behavior via a `.env` file or system environment variables:

```env
# LLM Backend
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
LITMUS_MODEL=gpt-4o                     # or claude-3-5-sonnet, deepseek-coder

# Workflow Limits
LITMUS_MAX_RETRIES=3                    # Max replan cycles per patch
LITMUS_VERIFIER_TIMEOUT=30              # Seconds per verification step

# Tool Paths
SOLC_PATH=/usr/bin/solc
FORGE_PATH=/usr/bin/forge
```

### Config File (`litmus.toml`)

For persistent project-level configuration:

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

### CLI Integration with Agentic Coding Tools

Litmus exposes a clean CLI that any external agent (or human developer) can invoke:

```bash
# Repair a single contract
litmus repair --contract ./contracts/Vault.sol --finding ./audits/finding-001.txt

# Output JSON for machine parsing
litmus repair --contract Vault.sol --finding bug.txt --output json > result.json
```

**Example JSON output** (for agent-to-agent communication):

```json
{
  "status": "verified",
  "patch_path": "./patches/Vault_patched.sol",
  "verification": {
    "compiles": true,
    "exploit_neutralized": true,
    "invariants_held": ["shares_ratio", "total_supply"],
    "regressions": []
  },
  "attempts": 2
}
```

### Hooking Into Cursor / Continue

To use Litmus directly from your IDE agent:

1. Add a custom command to your `.cursorrules` or `continue/config.json`:

```json
{
  "commands": [
    {
      "name": "litmus-fix",
      "command": "litmus repair --contract ${file} --finding ${selectedText} --output json",
      "description": "Run Litmus autonomous remediation on selected finding"
    }
  ]
}
```

2. Your IDE agent can now trigger Litmus on any selected audit finding and receive the verified patch.

### Integrating with Aider / Multi-Agent Systems

Litmus can be invoked as a **subprocess tool** from larger orchestrators:

```python
import subprocess, json

def run_litmus(contract_path, finding_text):
    result = subprocess.run(
        ["litmus", "repair", "--contract", contract_path,
         "--finding", finding_text, "--output", "json"],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)
```

### Custom Planner & Executor Prompts

Advanced users can override the internal prompt templates by placing custom files in `./prompts/`:

- `planner_system.txt` – Root cause and invariant mapping guidance.
- `executor_patch.txt` – Code generation instruction template.
- `verifier_rules.txt` – Additional invariant rules to check.

---

## The Closed-Loop Architecture

```text
                         ┌───────────────────────┐
                         │    AUDIT FINDING      │
                         └───────────┬───────────┘
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │      ORCHESTRATOR     │
                         └───────────┬───────────┘
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │   PLANNER AGENT       │
                         │                       │
                         │ Root Cause            │
                         │ Attack Path           │
                         │ Invariants            │
                         └───────────┬───────────┘
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │      EXECUTOR         │
                         │                       │
                         │ AST Parser             │
                         │ Static Analyzer        │
                         │ Patch Tool             │
                         └───────────┬───────────┘
                                     │
                                     ▼
                              ┌─────────────┐
                              │   PATCH     │
                              └──────┬──────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │     INDEPENDENT VERIFIER       │
                    │                                │
                    │  Compilation                   │
                    │  Exploit PoC                   │
                    │  Invariants                    │
                    │  Functional Regression         │
                    └───────────────┬────────────────┘
                                    │
                         ┌──────────┴──────────┐
                         │                     │
                       PASS                  FAIL
                         │                     │
                         ▼                     ▼
                 ┌──────────────┐       ┌──────────────┐
                 │ VERIFIED     │       │ DIAGNOSTIC   │
                 │ PATCH        │       │ FEEDBACK     │
                 └──────────────┘       └──────┬───────┘
                                               │
                                               ▼
                                          ┌──────────┐
                                          │ REPLAN   │
                                          └────┬─────┘
                                               │
                                               └──────→ Retry
```

The important difference is simple:

> **Litmus does not ask an agent to be right on the first attempt. It gives the agent a mechanism for discovering that it is wrong and correcting itself.**

---

## Controlled Experimental Results

We tested the architecture using a controlled five-stage experimental ladder, changing one architectural variable at a time.

| Version                  | Intervention                        |        RSR |
| ------------------------ | ----------------------------------- | ---------: |
| **V0 — Baseline**        | Single-turn direct prompt           |  **18.8%** |
| **V1 — Tools Only**      | AST Parser + Static Analyzer        |  **31.2%** |
| **V2 — Planner + State** | Multi-Step Planner + Explicit State |  **93.8%** |
| **V3 — Verifier Gate**   | Independent Verification            | **100.0%** |
| **Final — Closed Loop**  | Verification + Replanning           | **100.0%** |

The largest jump came from adding structured planning and workflow state:

```text
18.8%
  ↓
31.2%
  ↓
93.8%
  ↓
100.0%
```

The final system achieved **100% Remediation Success Rate (16/16)** compared with **18.8% (3/16)** for the single-turn baseline.  
That is an **81.25 percentage-point absolute improvement** and a **433.3% relative improvement** over baseline.

---

## What the Results Tell Us

The experiment suggests that the core problem is not simply that LLMs cannot write security patches. They can.

The problem is that **patch generation without structured reasoning and independent verification is unreliable**.

The experimental ladder makes this visible:

- **Tools Alone**: Adding static tools improved performance from **18.8% → 31.2%**. Useful, but insufficient.
- **Planning + State**: Adding structured planning and explicit workflow state increased performance to **93.8%**. This was the largest architectural improvement.
- **Independent Verification**: Adding the verifier gate pushed the system to **100%**.
- **Closed-Loop Replanning**: The final architecture retains the verifier feedback and uses it to drive another remediation attempt rather than simply rejecting the patch.

---

## Measured Results

All metrics are computed on the frozen 16-case benchmark suite using the deterministic Layer C evaluation scorer.

```text
=============================================================================================
Micro1 Evaluation: Experimental Ladder vs Baseline
=============================================================================================
Version           RSR       Exploit Neutralization    Invariants
---------------------------------------------------------------------------------------------
V0 Baseline       18.8%            18.8%                87.5%
V1 Tools Only     31.2%            31.2%                93.8%
V2 Planner+State  93.8%            93.8%               100.0%
V3 Verifier       100.0%           100.0%              100.0%
Final ClosedLoop  100.0%           100.0%              100.0%
=============================================================================================
```

### Remediation Success Rate

**18.8% → 100.0%**

### Exploit Neutralization

**18.8% → 100.0%**

### Invariant Preservation

**100.0%** in the final evaluation, with zero regressions on the tested standard deposit/withdraw flows.

### Deterministic Evaluation Latency

**< 0.1 seconds**

---

## Why This Matters

Smart contract security has traditionally focused heavily on **finding vulnerabilities**. But finding the bug is only half the problem.

Once a critical finding exists, engineering teams still have to make a difficult decision:

> **How quickly can we fix this without breaking the protocol?**

Move too slowly, and the vulnerability remains exposed.  
Move too quickly, and the patch itself can create a new failure mode.

Litmus attacks this remediation bottleneck directly. It provides a system that can:

```text
Understand the finding
        ↓
Reason about the attack
        ↓
Map the invariants
        ↓
Generate a patch
        ↓
Test the patch
        ↓
Diagnose failure
        ↓
Replan
        ↓
Verify again
        ↓
Return a verified candidate
```

The goal is not to replace security auditors. The goal is to make the period **after the audit and before deployment** dramatically safer and faster.

---

## Getting Started

Reproduce the full experimental ladder in under 5 seconds with zero external dependencies.

```bash
# Clone repository
git clone https://github.com/litmus/litmus.git
cd litmus

# Install dependencies
uv sync

# Configure your environment (copy and edit)
cp .env.example .env

# Run test suite
uv run pytest -v

# Run the full experimental ladder
uv run python -m experiments.runner

# Run the interactive demo
uv run python demo.py case_01
```

---

## The Core Insight

> **The hard part of smart contract remediation is not generating a patch. It is proving that the patch actually fixes the vulnerability without breaking the protocol.**

A single-turn LLM generates an answer.  
Litmus generates a **candidate, tests it, learns from failure, and verifies the result**.

That distinction turns remediation from:

```text
Generate → Trust
```

into:

```text
Generate → Verify → Diagnose → Replan → Verify
```

**That is the closed loop.**
```
