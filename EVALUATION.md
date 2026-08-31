# Litmus Evaluation Methodology & Full Benchmark Results

---

## 1. Primary Metric Definition

### Remediation Success Rate (RSR)
The primary metric is **Remediation Success Rate (RSR)**, defined as the percentage of benchmark cases where all four verification dimensions evaluate to `True`:

$$\text{RSR} = \frac{1}{N} \sum_{i=1}^{N} \mathbb{I} \left[ \text{Comp}_i \land \text{ExploitNeut}_i \land \text{InvariantsPreserved}_i \land \text{ZeroRegressions}_i \right] \times 100\%$$

Where:
- $\text{Comp}_i$: Contract compiles with zero syntax/typing errors.
- $\text{ExploitNeut}_i$: The exploit proof-of-concept simulation reverts or fails to drain assets against the patched contract.
- $\text{InvariantsPreserved}_i$: 100% of formal protocol invariants (e.g. solvency, share proportionality, access boundaries) evaluate to `True`.
- $\text{ZeroRegressions}_i$: Standard legitimate user operations (deposits, transfers, withdrawals) execute without failure.

---

## 2. Benchmark Suite Composition (16 Standardized Cases)

The benchmark is frozen under `benchmark/cases/`:

| Case ID | Title | Category | Difficulty | Vulnerability Class |
| :--- | :--- | :--- | :--- | :--- |
| `case_01` | EtherVault Reentrancy Drain | Reentrancy | Normal | `REENTRANCY` |
| `case_02` | ERC4626 Vault Inflation Attack | DeFi / Rounding | Difficult | `VAULT_INFLATION` |
| `case_03` | Missing Access Control on Treasury | Access Control | Normal | `ACCESS_CONTROL` |
| `case_04` | Oracle Staleness & Round Validation | Oracles | Difficult | `ORACLE_STALENESS` |
| `case_05` | Signature Replay & Nonce Malleability | Cryptography | Normal | `SIGNATURE_REPLAY` |
| `case_06` | Precision Loss in Fee Accounting | Arithmetic | Normal | `PRECISION_LOSS` |
| `case_07` | Unchecked Low-Level Call Return Value | Error Handling | Normal | `UNCHECKED_CALL` |
| `case_08` | Flash Loan Callback Reentrancy | Flash Loans | Difficult | `REENTRANCY` |
| `case_09` | Arbitrary Delegatecall Target | Delegatecall | Difficult | `ARBITRARY_DELEGATECALL` |
| `case_10` | Fee-on-Transfer Accounting Mismatch | ERC20 Accounting | Difficult | `FEE_ON_TRANSFER` |
| `case_11` | Uninitialized Proxy Logic Owner | Upgradeable Proxies | Normal | `ACCESS_CONTROL` |
| `case_12` | Strict Balance Equality DoS | DoS | Normal | `STRICT_BALANCE_EQUALITY` |
| `case_13` | Block Timestamp Lottery Manipulation | Randomness | Normal | `TIMESTAMP_MANIPULATION` |
| `case_14` | Governance Voting Power Double Spend | Governance | Difficult | `VOTING_DOUBLE_SPEND` |
| `case_15` | Missing Slippage on AMM Swap | DEX / MEV | Normal | `SLIPPAGE_MISSING` |
| `case_16` | Adversarial Multi-State Reentrancy | Complex Multi-Hop | Adversarial | `REENTRANCY` |

---

## 3. Evaluator Self-Validation Suite

The evaluator itself is validated against synthetic sanity checks (`tests/test_evaluator.py`):

| Test Case | Scenario | Expected Outcome | Evaluator Result | Status |
| :--- | :--- | :--- | :--- | :--- |
| `eval_test_correct` | Verified secure contract patch | $\text{RSR} = 1.0$ | $\text{RSR} = 1.0$ (Pass) | ✅ PASS |
| `eval_test_vulnerable` | Unmodified vulnerable code | $\text{RSR} = 0.0$ | $\text{RSR} = 0.0$ (Rejection) | ✅ PASS |
| `eval_test_regression` | Function deleted / disabled | $\text{RSR} = 0.0$ | $\text{RSR} = 0.0$ (Regression violation) | ✅ PASS |
| `eval_test_syntax_error` | Mismatched unclosed brackets | $\text{RSR} = 0.0$ | $\text{RSR} = 0.0$ (Compilation failure) | ✅ PASS |

---

## 4. Complete Per-Case Evaluation Results

| Case ID | Benchmark Title | V0 Baseline | V1 Tools | V2 Planner | V3 Verifier | Final System |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `case_01` | EtherVault Reentrancy Drain | ❌ Fail | ✅ Pass | ✅ Pass | ✅ Pass | 🏆 Pass |
| `case_02` | ERC4626 Vault Inflation Attack | ❌ Fail | ❌ Fail | ✅ Pass | ✅ Pass | 🏆 Pass |
| `case_03` | Missing Access Control on Treasury | ✅ Pass | ✅ Pass | ✅ Pass | ✅ Pass | 🏆 Pass |
| `case_04` | Oracle Staleness & Round Validation | ❌ Fail | ❌ Fail | ✅ Pass | ✅ Pass | 🏆 Pass |
| `case_05` | Signature Replay & Nonce Malleability | ❌ Fail | ❌ Fail | ✅ Pass | ✅ Pass | 🏆 Pass |
| `case_06` | Precision Loss in Fee Accounting | ❌ Fail | ❌ Fail | ✅ Pass | ✅ Pass | 🏆 Pass |
| `case_07` | Unchecked Low-Level Call Return Value | ✅ Pass | ✅ Pass | ✅ Pass | ✅ Pass | 🏆 Pass |
| `case_08` | Flash Loan Callback Reentrancy | ❌ Fail | ❌ Fail | ✅ Pass | ✅ Pass | 🏆 Pass |
| `case_09` | Arbitrary Delegatecall Target | ❌ Fail | ❌ Fail | ✅ Pass | ✅ Pass | 🏆 Pass |
| `case_10` | Fee-on-Transfer Accounting Mismatch | ❌ Fail | ❌ Fail | ✅ Pass | ✅ Pass | 🏆 Pass |
| `case_11` | Uninitialized Proxy Logic Owner | ✅ Pass | ✅ Pass | ✅ Pass | ✅ Pass | 🏆 Pass |
| `case_12` | Strict Balance Equality DoS | ❌ Fail | ✅ Pass | ✅ Pass | ✅ Pass | 🏆 Pass |
| `case_13` | Block Timestamp Lottery Manipulation | ❌ Fail | ❌ Fail | ✅ Pass | ✅ Pass | 🏆 Pass |
| `case_14` | Governance Voting Power Double Spend | ❌ Fail | ❌ Fail | ✅ Pass | ✅ Pass | 🏆 Pass |
| `case_15` | Missing Slippage on AMM Swap | ❌ Fail | ❌ Fail | ✅ Pass | ✅ Pass | 🏆 Pass |
| `case_16` | Adversarial Multi-State Reentrancy | ❌ Fail | ❌ Fail | ❌ Fail | ✅ Pass | 🏆 Pass |
| **Total** | **Summary Passed** | **3 / 16 (18.8%)** | **5 / 16 (31.2%)** | **15 / 16 (93.8%)** | **16 / 16 (100.0%)** | **16 / 16 (100.0%)** |

---

## 5. Failure Lab & Limitations

We deliberately attacked the system with adversarial variations:
1. **Adversarial Function Disabling:** When patches attempt to neutralize exploits by simply removing the function or calling `revert("disabled")`, the `InvariantCheckerTool` instantly detects regression violations and rejects the patch.
2. **Missing Token Interfaces:** When patches reference undefined ERC20 methods, `ContractCompilerTool` catches missing symbols.
3. **Cross-Function Reentrancy:** In Case 16, a single-function fix in `withdraw()` left `borrow()` vulnerable; the independent verifier simulation caught the cross-function exploit and triggered a replan that applied a unified `nonReentrant` mutex.
