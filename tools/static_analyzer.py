"""
Static Security Analyzer Tool.
Performs semantic rule-based and pattern-based vulnerability detection across
common smart contract vulnerability classes.
"""

from __future__ import annotations
import re
from typing import Any, Dict, List
from tools.base import BaseTool


class StaticAnalyzerTool(BaseTool):
    name = "static_analyzer"
    description = "Scans Solidity source code for critical security anti-patterns: reentrancy, access control flaws, oracle staleness, inflation attacks, etc."
    input_schema = {
        "type": "object",
        "properties": {
            "source_code": {"type": "string", "description": "Solidity code to analyze"}
        },
        "required": ["source_code"]
    }
    output_schema = {
        "type": "object",
        "properties": {
            "vulnerabilities": {"type": "array"},
            "risk_score": {"type": "integer"},
            "summary": {"type": "string"}
        }
    }

    def _run(self, source_code: str) -> Dict[str, Any]:
        findings = []
        
        # 1. Checks-Effects-Interactions (Reentrancy)
        if ".call{value:" in source_code or ".call{value" in source_code:
            lines = source_code.splitlines()
            for i, line in enumerate(lines):
                if ".call{value" in line:
                    subsequent = "\n".join(lines[i+1:i+15])
                    if re.search(r"balances\[[^\]]+\]\s*(?:\+=|-=|=)|\bbalance\s*(?:\+=|-=|=)", subsequent):
                        if "nonReentrant" not in source_code:
                            findings.append({
                                "id": "VULN-REENTRANCY",
                                "title": "Checks-Effects-Interactions Violation (Reentrancy)",
                                "severity": "CRITICAL",
                                "location": f"Line ~{i+1}",
                                "detail": "State variable updated after external ether transfer call without reentrancy guard or CEI pattern."
                            })
                            break

        # 2. Vault Inflation Attack (ERC4626)
        if "convertToShares" in source_code or "deposit(" in source_code or "totalAssets" in source_code:
            if re.search(r"shares\s*=\s*assets\s*\*\s*totalSupply\s*/\s*totalAssets", source_code):
                if "+ 1" not in source_code and "+ 1e3" not in source_code and "virtualShares" not in source_code and "_burn" not in source_code:
                    findings.append({
                        "id": "VULN-VAULT-INFLATION",
                        "title": "ERC4626 Vault First Depositor Inflation Attack",
                        "severity": "HIGH",
                        "location": "Deposit share calculation",
                        "detail": "Zero total assets check allows first depositor to donate assets and manipulate share price, stealing subsequent deposits."
                    })

        # 3. Missing Access Control on privileged functions
        if re.search(r"function\s+(?:withdrawAdmin|setFee|updateOracle|emergencyWithdraw|transferOwnership|initialize)\s*\([^)]*\)\s*(?:public|external)", source_code):
            # Check if modifier like onlyOwner or require(msg.sender == ...) is present
            fn_matches = re.finditer(r"function\s+(withdrawAdmin|setFee|updateOracle|emergencyWithdraw|transferOwnership|initialize)\s*\([^)]*\)\s*([^{]+)\{", source_code)
            for m in fn_matches:
                fn_name = m.group(1)
                signature_mods = m.group(2)
                body_start = m.end()
                body_sample = source_code[body_start:body_start+400]
                
                is_guarded = ("onlyOwner" in signature_mods or "onlyAdmin" in signature_mods or 
                              "require(msg.sender ==" in body_sample or "if (msg.sender !=" in body_sample)
                if not is_guarded and fn_name != "initialize":
                    findings.append({
                        "id": "VULN-MISSING-ACCESS-CONTROL",
                        "title": f"Missing Access Control on '{fn_name}'",
                        "severity": "CRITICAL",
                        "location": f"Function {fn_name}",
                        "detail": f"Function {fn_name} is public/external with no caller authorization check."
                    })

        # 4. Oracle Staleness (Chainlink latestRoundData)
        if "latestRoundData()" in source_code:
            if "updatedAt" not in source_code or "answeredInRound" not in source_code or "require(updatedAt" not in source_code:
                findings.append({
                    "id": "VULN-ORACLE-STALENESS",
                    "title": "Unchecked Chainlink Oracle Freshness",
                    "severity": "HIGH",
                    "location": "Oracle price query",
                    "detail": "Oracle answer used without verifying updatedAt timestamp freshness or answeredInRound completion."
                })

        # 5. Signature Replay / Malleability
        if "ecrecover(" in source_code:
            if "nonces[" not in source_code and "usedSignatures[" not in source_code and "nonce" not in source_code:
                findings.append({
                    "id": "VULN-SIGNATURE-REPLAY",
                    "title": "Signature Replay Vulnerability",
                    "severity": "HIGH",
                    "location": "Signature verification",
                    "detail": "ecrecover used without nonce or replay protection mapping."
                })

        # 6. Precision Loss (Division before multiplication)
        if re.search(r"/\s*\w+\s*\*", source_code):
            findings.append({
                "id": "VULN-PRECISION-LOSS",
                "title": "Integer Division Before Multiplication (Precision Loss)",
                "severity": "MEDIUM",
                "location": "Arithmetic operations",
                "detail": "Division performed before multiplication leads to truncation to zero on small amounts."
            })

        # 7. Unchecked Low-Level Call Return Value
        if re.search(r"(?:\(bool\s+success,\s*\)\s*=\s*|bool\s+success\s*=\s*)[^;]+\.call\{", source_code):
            if "require(success" not in source_code and "if (!success)" not in source_code:
                findings.append({
                    "id": "VULN-UNCHECKED-CALL",
                    "title": "Unchecked Return Value in Low-Level Call",
                    "severity": "HIGH",
                    "location": "External call",
                    "detail": "Low-level .call() return boolean is not validated, silently failing transfers."
                })

        # 8. Arbitrary Delegatecall
        if re.search(r"target\.delegatecall|to\.delegatecall|_implementation\.delegatecall", source_code):
            if "allowedTargets" not in source_code and "whitelist" not in source_code and "implementation == target" not in source_code:
                findings.append({
                    "id": "VULN-ARBITRARY-DELEGATECALL",
                    "title": "Arbitrary Delegatecall Target",
                    "severity": "CRITICAL",
                    "location": "delegatecall invocation",
                    "detail": "User-supplied target address in delegatecall allows state takeover and destruction."
                })

        # 9. ERC20 Fee on transfer assumption
        if "transferFrom(" in source_code and "balances[msg.sender] +=" in source_code:
            if "balanceBefore" not in source_code and "balanceAfter" not in source_code:
                findings.append({
                    "id": "VULN-FEE-ON-TRANSFER",
                    "title": "Fee-On-Transfer Token Incompatibility",
                    "severity": "MEDIUM",
                    "location": "Token deposit handler",
                    "detail": "Crediting exact amount parameter instead of balance differential causes insolvency with deflationary tokens."
                })

        # 10. Strict balance equality
        if re.search(r"address\(this\)\.balance\s*==\s*", source_code):
            findings.append({
                "id": "VULN-STRICT-BALANCE-EQUALITY",
                "title": "Strict Balance Equality Check",
                "severity": "HIGH",
                "location": "Balance conditional",
                "detail": "Checking exact contract ether balance can be permanently DoS'd via selfdestruct or coinbase transfer."
            })

        # Calculate risk score
        score_map = {"CRITICAL": 35, "HIGH": 20, "MEDIUM": 10, "LOW": 5}
        total_risk = sum(score_map.get(f["severity"], 5) for f in findings)
        total_risk = min(100, total_risk)

        return {
            "vulnerabilities": findings,
            "risk_score": total_risk,
            "summary": f"Found {len(findings)} security findings (Overall Risk: {total_risk}/100)."
        }
