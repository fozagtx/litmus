"""
Planning Prompts (Layer A Planner).
Directs the planner agent to perform root cause analysis, identify invariants,
and formulate a multi-step remediation plan.
"""

PLANNER_SYSTEM_PROMPT = """You are a Lead Smart Contract Security Architect and Planner.
Your goal is to analyze a vulnerable smart contract, its exploit PoC, and protocol invariants,
then formulate an explicit, step-by-step remediation plan with clear invariants and tool milestones.

You must output a structured JSON plan with:
- objective: Concise summary of what needs to be fixed.
- vulnerability_hypothesis: Deep root-cause explanation of how the exploit functions.
- target_invariants: List of critical invariants that MUST NOT be broken.
- steps: Array of plan steps (step_id, name, description, tool_required, expected_output)."""

PLANNER_USER_PROMPT_TEMPLATE = """Analyze the following vulnerable contract and develop a structured remediation plan.

CONTRACT NAME: {contract_name}
VULNERABILITY DESCRIPTION: {vulnerability_description}

EXPLOIT POC:
```solidity
{exploit_poc}
```

REQUIRED INVARIANTS:
{invariants}

VULNERABLE CODE:
```solidity
{vulnerable_code}
```

Output your plan strictly in valid JSON format matching the schema:
{{
  "objective": "...",
  "vulnerability_hypothesis": "...",
  "target_invariants": ["..."],
  "steps": [
    {{
      "step_id": 1,
      "name": "...",
      "description": "...",
      "tool_required": "ast_parser|static_analyzer|contract_compiler|exploit_runner|invariant_checker|patch_tool",
      "expected_output": "..."
    }}
  ]
}}"""

REPLAN_PROMPT_TEMPLATE = """The previous patch attempt failed verification.

PREVIOUS ATTEMPT DIAGNOSTICS:
{verification_diagnostics}

ACTIONABLE FEEDBACK:
{actionable_feedback}

FAILURES OBSERVED:
{failures}

Formulate a revised remediation plan addressing the exact root cause of the verification failure.
Return the updated plan JSON:"""
