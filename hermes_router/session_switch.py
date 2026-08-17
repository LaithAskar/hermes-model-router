"""Permission-bound, fail-closed switching for an active Hermes session."""

from dataclasses import dataclass
from typing import Any, Protocol

from .approval import ApprovalResult
from .router import RouteDecision


class SessionSwitchError(RuntimeError):
    """The session switch was refused or could not be verified."""


@dataclass(frozen=True)
class SessionSnapshot:
    session_id: str
    provider: str
    model: str
    running: bool
    active: bool


@dataclass(frozen=True)
class SessionSwitchApproval:
    route: ApprovalResult
    expected: SessionSnapshot
    scope: str = "session"


@dataclass(frozen=True)
class SessionSwitchResult:
    switched: bool
    before: SessionSnapshot
    after: SessionSnapshot
    response: Any = None


class SessionTransport(Protocol):
    def get_session(self, session_id: str) -> SessionSnapshot:
        ...

    def switch_session_model(self, session_id: str, provider: str, model: str) -> Any:
        ...


def _same_route(left: SessionSnapshot, right: SessionSnapshot) -> bool:
    return (
        left.session_id == right.session_id
        and left.provider == right.provider
        and left.model == right.model
    )


def switch_approved_session(
    decision: RouteDecision,
    approval: SessionSwitchApproval,
    transport: SessionTransport,
    *,
    session_id: str = "",
) -> SessionSwitchResult:
    """Revalidate, switch, then verify one active non-running session.

    The transport must implement Hermes' native session-scoped switch. This
    function never writes global configuration and never retries a failed
    mutation automatically.
    """
    if not isinstance(approval, SessionSwitchApproval):
        raise SessionSwitchError("session switch requires a bound approval")
    if approval.scope != "session":
        raise SessionSwitchError("only session-scoped switching is allowed")
    if approval.route.decision != decision:
        raise SessionSwitchError("approval is not bound to this route")
    if not approval.route.approved:
        return SessionSwitchResult(False, approval.expected, approval.expected)

    target_session = session_id or approval.expected.session_id
    if not target_session or target_session != approval.expected.session_id:
        raise SessionSwitchError("approval is not bound to this session")

    current = transport.get_session(target_session)
    if not current.active:
        raise SessionSwitchError("target session is not active")
    if current.running:
        raise SessionSwitchError("target session is busy")
    if not _same_route(current, approval.expected):
        raise SessionSwitchError("stale approval: current route changed")

    response = transport.switch_session_model(
        target_session,
        decision.profile.provider,
        decision.profile.model,
    )
    if isinstance(response, dict) and response.get("error"):
        error = response.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise SessionSwitchError(message or "Hermes model switch failed")

    after = transport.get_session(target_session)
    if not after.active or after.running:
        raise SessionSwitchError("post-switch session state is invalid")
    if (after.provider, after.model) != (
        decision.profile.provider,
        decision.profile.model,
    ):
        raise SessionSwitchError("post-switch verification failed")
    return SessionSwitchResult(True, current, after, response)
