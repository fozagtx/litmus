"""
Feedback & Re-planning Prompts.
Standardized templates for failure classification and iterative feedback loops.
"""

FEEDBACK_REPAIR_TEMPLATE = """VERIFICATION FEEDBACK FOR RETRY #{retry_number}

The verifier identified the following critical issues:
- Primary Failure: {failure_classification}
- Details: {actionable_feedback}
- Suggested Fix Strategy: {suggested_fix_strategy}

REVISE YOUR REMEDIATION:
Ensure that you address this specific failure without breaking existing invariant requirements."""
