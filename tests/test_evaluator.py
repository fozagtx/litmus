"""
Evaluator Self-Validation Suite.
Tests the evaluator itself on known synthetic edge cases:
- Obviously correct solution
- Obviously incorrect / vulnerable solution
- Regression-inducing solution (e.g. disabled function)
- Syntax / Compilation error
- Missing invariants
"""

import pytest
from benchmark.schema import BenchmarkCase, RegressionTestCase
from evaluation.scorer import BenchmarkScorer


@pytest.fixture
def test_case():
    return BenchmarkCase(
        case_id="eval_test_01",
        title="Evaluator Test Vault",
        category="Reentrancy",
        difficulty="Normal",
        vulnerability_type="REENTRANCY",
        vulnerable_code="contract Test { mapping(address=>uint) public balances; function withdraw() external { (bool s, ) = msg.sender.call{value:1}(\"\"); balances[msg.sender]=0; } }",
        vulnerability_description="CEI violation",
        exploit_poc="Attacker drains vault",
        invariants=["Solvency: sum(balances) <= address(this).balance", "Legitimate user withdrawal"],
        regression_tests=[RegressionTestCase(name="Withdraw flow", description="User withdraws", function_called="withdraw")],
        constraints=[]
    )


def test_evaluator_obviously_correct(test_case):
    scorer = BenchmarkScorer()
    correct_patch = "contract Test { mapping(address=>uint) public balances; function withdraw() external { balances[msg.sender]=0; (bool s, ) = msg.sender.call{value:1}(\"\"); } }"
    res = scorer.evaluate_case(case=test_case, patch_code=correct_patch, version="Test_Correct")
    assert res.compilation_passed is True
    assert res.exploit_neutralized is True
    assert res.all_invariants_passed is True
    assert res.zero_regressions is True
    assert res.is_success is True


def test_evaluator_obviously_incorrect_vulnerable(test_case):
    scorer = BenchmarkScorer()
    # Unchanged vulnerable code
    res = scorer.evaluate_case(case=test_case, patch_code=test_case.vulnerable_code, version="Test_Vuln")
    assert res.exploit_neutralized is False
    assert res.is_success is False


def test_evaluator_regression_inducing_disabled_function(test_case):
    scorer = BenchmarkScorer()
    # Naive LLM fix: delete withdraw function entirely
    broken_patch = "contract Test { mapping(address=>uint) public balances; }"
    res = scorer.evaluate_case(case=test_case, patch_code=broken_patch, version="Test_Regression")
    assert res.zero_regressions is False
    assert res.is_success is False


def test_evaluator_syntax_error(test_case):
    scorer = BenchmarkScorer()
    syntax_error_patch = "contract Test { unclosed brackets { {"
    res = scorer.evaluate_case(case=test_case, patch_code=syntax_error_patch, version="Test_Syntax")
    assert res.compilation_passed is False
    assert res.is_success is False
