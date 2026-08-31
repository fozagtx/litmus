"""
Workflow Verification Module.
Provides verification wrappers and failure dispatch.
"""

from __future__ import annotations
from typing import TYPE_CHECKING
from workflow.state import WorkflowState, VerificationReport

if TYPE_CHECKING:
    from agents.verifier import VerifierAgent


def verify_workflow_state(state: WorkflowState, verifier: VerifierAgent = None) -> VerificationReport:
    if verifier is None:
        from agents.verifier import VerifierAgent
        verifier = VerifierAgent()
    return verifier.verify_patch(state)
