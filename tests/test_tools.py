"""
Unit Tests for Security & Analysis Tools.
"""

import pytest
from tools.ast_parser import ASTParserTool
from tools.static_analyzer import StaticAnalyzerTool
from tools.contract_compiler import ContractCompilerTool
from tools.exploit_runner import ExploitRunnerTool
from tools.invariant_checker import InvariantCheckerTool
from tools.patch_tool import PatchTool


def test_ast_parser_tool():
    tool = ASTParserTool()
    solidity_code = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
contract Token {
    mapping(address => uint256) public balances;
    function transfer(address to, uint256 amount) public returns (bool) {
        balances[msg.sender] -= amount;
        balances[to] += amount;
        return true;
    }
}"""
    res = tool.execute(source_code=solidity_code)
    assert res.success is True
    assert len(res.output["contracts"]) == 1
    assert res.output["contracts"][0]["name"] == "Token"
    assert len(res.output["functions"]) == 1
    assert res.output["functions"][0]["name"] == "transfer"


def test_static_analyzer_tool():
    tool = StaticAnalyzerTool()
    vuln_code = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
contract Vault {
    mapping(address => uint256) public balances;
    function withdraw() external {
        uint256 b = balances[msg.sender];
        (bool s, ) = msg.sender.call{value: b}("");
        balances[msg.sender] = 0;
    }
}"""
    res = tool.execute(source_code=vuln_code)
    assert res.success is True
    assert len(res.output["vulnerabilities"]) >= 1
    assert res.output["vulnerabilities"][0]["id"] == "VULN-REENTRANCY"


def test_contract_compiler_tool():
    tool = ContractCompilerTool()
    valid_code = "pragma solidity ^0.8.20; contract Test { uint256 public x = 1; }"
    res = tool.execute(source_code=valid_code)
    assert res.success is True
    assert res.output["compiled_successfully"] is True

    invalid_code = "pragma solidity ^0.8.20; contract Test { uint256 public x = 1; "
    res_err = tool.execute(source_code=invalid_code)
    assert res_err.success is True
    assert res_err.output["compiled_successfully"] is False
    assert len(res_err.output["errors"]) >= 1


def test_exploit_runner_tool():
    tool = ExploitRunnerTool()
    vuln_code = """contract Vault {
        function withdraw() external {
            (bool s, ) = msg.sender.call{value: 1}("");
            balances[msg.sender] = 0;
        }
    }"""
    res_vuln = tool.execute(source_code=vuln_code, exploit_type="REENTRANCY")
    assert res_vuln.output["exploit_neutralized"] is False

    safe_code = """contract Vault {
        function withdraw() external {
            balances[msg.sender] = 0;
            (bool s, ) = msg.sender.call{value: 1}("");
        }
    }"""
    res_safe = tool.execute(source_code=safe_code, exploit_type="REENTRANCY")
    assert res_safe.output["exploit_neutralized"] is True


def test_invariant_checker_tool():
    tool = InvariantCheckerTool()
    code = """contract Vault {
        mapping(address => uint256) public balances;
        function withdraw() external { balances[msg.sender] = 0; }
    }"""
    res = tool.execute(
        source_code=code,
        invariants=["Solvency: sum(balances) <= address(this).balance", "Legitimate user withdrawal"],
        regression_tests=[{"name": "test_withdraw", "function_called": "withdraw"}]
    )
    assert res.success is True
    assert res.output["all_passed"] is True
    assert res.output["invariants_passed"] == 2
    assert res.output["regressions_passed"] == 1


def test_patch_tool():
    tool = PatchTool()
    original = "contract Test { function old() public {} }"
    replacement = "contract Test { function updated() public {} }"
    res = tool.execute(original_code=original, replacement_code=replacement)
    assert res.success is True
    assert "updated" in res.output["patched_code"]
