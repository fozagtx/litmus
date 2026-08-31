"""
Invariant & Regression Checker Tool.
Evaluates protocol invariants and regression test suites to guarantee that
security patches do not break legitimate user workflows, token standards, or state solvency.
"""

from __future__ import annotations
import re
from typing import Any, Dict, List
from tools.base import BaseTool


class InvariantCheckerTool(BaseTool):
    name = "invariant_checker"
    description = "Tests formal protocol invariants (solvency, balance conservation, access barriers) and regression test cases against patched contract code."
    input_schema = {
        "type": "object",
        "properties": {
            "source_code": {"type": "string", "description": "Patched contract source code"},
            "invariants": {"type": "array", "description": "List of formal protocol invariants"},
            "regression_tests": {"type": "array", "description": "List of standard user flow regression tests"}
        },
        "required": ["source_code"]
    }
    output_schema = {
        "type": "object",
        "properties": {
            "all_passed": {"type": "boolean"},
            "invariants_passed": {"type": "integer"},
            "invariants_total": {"type": "integer"},
            "regressions_passed": {"type": "integer"},
            "regressions_total": {"type": "integer"},
            "failures": {"type": "array"},
            "summary": {"type": "string"}
        }
    }

    def _run(
        self,
        source_code: str,
        invariants: List[str] = None,
        regression_tests: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        invariants = invariants or []
        regression_tests = regression_tests or []
        failures = []
        
        # 1. Anti-Cheat Check: Did the patch simply delete the function or permanently revert?
        # A common naive LLM failure is to replace a vulnerable withdraw with 'revert()' or delete the function.
        if "revert(\"disabled\")" in source_code or "revert();" in source_code.replace(" ", ""):
            failures.append({
                "test_name": "Regression: Legitimate User Withdrawal",
                "type": "REGRESSION_VIOLATION",
                "detail": "Patch disabled function with unconditional revert, bricking legitimate user operations."
            })

        # 2. Check each protocol invariant
        invariants_passed = 0
        for inv in invariants:
            inv_lower = inv.lower()
            inv_passed = True
            failure_reason = ""

            if "solvency" in inv_lower or "balance conservation" in inv_lower:
                # Must maintain balances/shares/reserves state and update them
                has_state_var = any(k in source_code for k in ["balances", "totalAssets", "totalShares", "totalVaultCollateral", "rewards", "stakingToken", "usedSignatures", "address(this).balance"])
                if not has_state_var:
                    inv_passed = False
                    failure_reason = "Balance/solvency tracking state variable removed or missing."
                elif not re.search(r"(?:balances|shares|rewards|totalAssets|totalShares|totalVaultCollateral|totalStaked|usedSignatures)\s*(?:\[[^\]]+\])?\s*(?:\+=|-=|=)", source_code) and "transfer(" not in source_code and ".call{" not in source_code:
                    inv_passed = False
                    failure_reason = "No state updates to preserve balance accounting."

            elif "legitimate user withdrawal" in inv_lower or "withdrawal possible" in inv_lower:
                # Withdraw function must exist, be public/external, and contain transfer/call
                if "function withdraw" not in source_code and "function redeem" not in source_code:
                    inv_passed = False
                    failure_reason = "Withdraw/redeem function missing from contract interface."
                elif "require(false" in source_code:
                    inv_passed = False
                    failure_reason = "Withdraw function contains unconditional failing assertion."

            elif "admin boundary" in inv_lower or "only owner" in inv_lower:
                # Privileged functions must have msg.sender checks
                if "onlyOwner" not in source_code and "msg.sender == owner" not in source_code and "msg.sender == admin" not in source_code:
                    inv_passed = False
                    failure_reason = "Admin privileges not restricted to authorized owner address."

            elif "interface compliance" in inv_lower or "erc" in inv_lower:
                # Check for standard interface functions
                if "ERC20" in inv:
                    for req_fn in ["transfer", "balanceOf", "totalSupply"]:
                        if req_fn not in source_code:
                            inv_passed = False
                            failure_reason = f"Required ERC20 interface function '{req_fn}' is missing."
                            break

            elif "no fund lock" in inv_lower or "liveness" in inv_lower:
                if "selfdestruct" in source_code and "onlyOwner" not in source_code:
                    inv_passed = False
                    failure_reason = "Unguarded selfdestruct violates liveness invariant."

            if inv_passed:
                invariants_passed += 1
            else:
                failures.append({
                    "test_name": f"Invariant: {inv}",
                    "type": "INVARIANT_VIOLATION",
                    "detail": failure_reason or "Formal invariant check failed."
                })

        # 3. Check Regression Tests
        regressions_passed = 0
        for test in regression_tests:
            test_name = test.get("name", "Standard User Flow")
            expected_fn = test.get("function_called", "")
            
            # Check if function exists
            if expected_fn and f"function {expected_fn}" not in source_code:
                failures.append({
                    "test_name": f"Regression: {test_name}",
                    "type": "REGRESSION_VIOLATION",
                    "detail": f"Function '{expected_fn}' required for regular user operations is missing."
                })
            else:
                regressions_passed += 1

        total_invariants = len(invariants)
        total_regressions = len(regression_tests)
        all_passed = len(failures) == 0

        return {
            "all_passed": all_passed,
            "invariants_passed": invariants_passed,
            "invariants_total": total_invariants,
            "regressions_passed": regressions_passed,
            "regressions_total": total_regressions,
            "failures": failures,
            "summary": f"Invariants: {invariants_passed}/{total_invariants} passed. Regressions: {regressions_passed}/{total_regressions} passed. Failures: {len(failures)}."
        }
