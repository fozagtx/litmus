# Litmus Reproduction Guide

Follow these steps to reproduce all benchmark scores, experimental ladder deltas, and evidence files from scratch.

---

## 1. Prerequisites & Environment

- **Operating System:** macOS, Linux, or Windows (WSL)
- **Python Version:** Python 3.10+ (tested on Python 3.14.7)
- **Package Manager:** `uv` (recommended) or `pip`

### Install uv (if not present)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## 2. Setup & Installation

Clone and install dependencies:
```bash
cd /Users/kaizen/Desktop/litmus

# Install dependencies into virtual environment
uv sync
```

---

## 3. Reproduction Commands

### Step 1: Run Full Test Suite (19/19 Tests)
Verifies workflow state, 6 security tools, agent interfaces, evaluator self-validation, and reproducibility:
```bash
PYTHONPATH=. uv run pytest -v
```
**Expected Output:** `19 passed in ~1.1 seconds`

---

### Step 2: Execute Full 5-Stage Experimental Ladder
Executes V0 Baseline, V1 Tools, V2 Planner, V3 Verifier, and Final Closed-Loop across the 16 frozen benchmark cases:
```bash
PYTHONPATH=. uv run python -m experiments.runner
```
**Expected Output:**
```text
==================================================
🚀 RUNNING LITMUS EXPERIMENTAL LADDER (16 BENCHMARK CASES)
==================================================

[1/5] Running V0 Baseline (Single-turn LLM)...
[2/5] Running V1 Tools-Only (Executor + AST/Static Analysis)...
[3/5] Running V2 Planner+State (Structured Plan + State Tracking)...
[4/5] Running V3 Verifier Gate (Layer B Verifier without Retry)...
[5/5] Running Final System (Closed-Loop Orchestrator + Verification + Replan/Retry)...

==================================================
📊 COMPUTING DELTAS AND COMPARATIVE METRICS
==================================================
             🔬 Micro1 Evaluation: Experimental Ladder vs Baseline              
┏━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━┓
┃ Version┃ Success┃   Δ Abs┃   Δ Rel┃ Compile┃ Exploit┃ Invar.┃ Retries┃   Time┃
┡━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━┩
│ V0_Base│  18.8% │      - │      - │ 100.0% │  18.8% │ 87.5% │    0.0 │ 0.08s │
│ V1_Tool│  31.2% │ +12.5% │ +66.7% │ 100.0% │  31.2% │ 93.8% │    0.0 │ 0.00s │
│ V2_Plan│  93.8% │ +75.0% │ +400.0%│ 100.0% │  93.8% │ 100.0%│    0.0 │ 0.00s │
│ V3_Veri│ 100.0% │ +81.25%│ +433.3%│ 100.0% │ 100.0% │ 100.0%│    0.0 │ 0.00s │
│ Final  │ 100.0% │ +81.25%│ +433.3%│ 100.0% │ 100.0% │ 100.0%│    0.0 │ 0.00s │
└────────┴────────┴────────┴────────┴────────┴────────┴───────┴────────┴───────┘
```

---

### Step 3: Run Interactive CLI Demo
Run the visual step-by-step interactive demo on any benchmark case:
```bash
# Reentrancy Case
PYTHONPATH=. uv run python demo.py case_01

# Vault Inflation Case
PYTHONPATH=. uv run python demo.py case_02

# Adversarial Multi-State Reorder Case
PYTHONPATH=. uv run python demo.py case_16
```

---

## 4. Evidence Inspection

After running `experiments.runner`, inspect the generated JSON files:
- Raw Baseline Results: `evidence/raw/results_V0_Baseline.json`
- Raw Final Results: `evidence/raw/results_Final_ClosedLoop.json`
- Processed Comparative Report: `evidence/processed/comparative_experiment_report.json`
- Trajectories: `trajectories/*.json`
