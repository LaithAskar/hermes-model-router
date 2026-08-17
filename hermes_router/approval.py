"""Permission gate for model-switch proposals.

This module only asks for consent. It deliberately does not mutate Hermes
configuration or start a gateway restart; an integration can consume the
approved decision and perform the provider-specific switch explicitly.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from .router import RouteDecision


@dataclass(frozen=True)
class ApprovalResult:
    approved: bool
    decision: RouteDecision
    message: str


def request_approval(
    decision: RouteDecision,
    current_provider: Optional[str] = None,
    current_model: Optional[str] = None,
    input_fn: Callable[[str], str] = input,
) -> ApprovalResult:
    current = "unknown model"
    if current_provider and current_model:
        current = f"{current_provider}/{current_model}"
    proposed = f"{decision.profile.provider}/{decision.profile.model}"
    prompt = (
        f"Route this {decision.task.value} task from {current} to {proposed}? "
        f"confidence={decision.confidence:.2f}; reason={decision.reason} [y/N] "
    )
    answer = input_fn(prompt).strip().lower()
    approved = answer in {"y", "yes"}
    message = f"switch approved: {proposed}" if approved else f"switch denied: staying on {current}"
    return ApprovalResult(approved=approved, decision=decision, message=message)
