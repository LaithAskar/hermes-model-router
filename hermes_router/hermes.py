"""Safe execution adapter for launching a routed Hermes task."""

from dataclasses import dataclass
import shutil
import subprocess
import re
from typing import Callable, List, Optional, Any

from .approval import ApprovalResult
from .router import RouteDecision


_MODEL_VALUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]*$")


def _validate_model_value(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or value.startswith("-") or not _MODEL_VALUE_RE.fullmatch(value):
        raise ValueError(f"unsafe {label} value")
    return value


@dataclass(frozen=True)
class HermesRunResult:
    approved: bool
    command: List[str]
    returncode: Optional[int]
    stdout: str
    stderr: str


def build_command(decision: RouteDecision, task: str, hermes_bin: str = "hermes") -> List[str]:
    """Build an argv list; never use a shell or interpolate task text."""
    provider = _validate_model_value(decision.profile.provider, "provider")
    model = _validate_model_value(decision.profile.model, "model")
    return [
        hermes_bin,
        "chat",
        "--provider",
        provider,
        "-m",
        model,
        "-Q",
        "-q",
        task,
    ]


def run_approved(
    decision: RouteDecision,
    task: str,
    *,
    approval: ApprovalResult,
    hermes_bin: Optional[str] = None,
    runner: Callable[..., Any] = subprocess.run,
) -> HermesRunResult:
    """Run a new routed Hermes task only after explicit approval.

    This intentionally starts a bounded new Hermes invocation rather than
    mutating config.yaml or silently changing a live conversation.
    """
    if not isinstance(approval, ApprovalResult) or approval.decision != decision:
        raise ValueError("execution requires the approval result for this exact route")
    if not approval.approved:
        return HermesRunResult(False, [], None, "", "switch denied; Hermes was not run")
    binary = hermes_bin or shutil.which("hermes")
    if not binary:
        raise FileNotFoundError("Hermes executable was not found on PATH")
    command = build_command(decision, task, binary)
    completed = runner(command, capture_output=True, text=True, check=False)
    return HermesRunResult(
        True,
        command,
        completed.returncode,
        completed.stdout or "",
        completed.stderr or "",
    )
