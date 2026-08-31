"""
Baseline Remediation Prompts (V0).
Standard single-turn direct prompt representing a conventional non-agentic LLM code assistant.
"""

BASELINE_SYSTEM_PROMPT = """You are a smart contract security assistant. 
You will be given a vulnerable Solidity smart contract and a description of the issue.
Provide a patched, secure version of the contract. Output ONLY the Solidity code."""

BASELINE_USER_PROMPT_TEMPLATE = """Please fix the security vulnerability in the following Solidity contract.

CONTRACT NAME: {contract_name}
VULNERABILITY DESCRIPTION: {vulnerability_description}

VULNERABLE CODE:
```solidity
{vulnerable_code}
```

Return the complete, secure Solidity contract code:"""
