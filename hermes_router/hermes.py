"""Safe execution adapter for launching a routed Hermes task."""

from dataclasses import dataclass
import shutil
import subprocess
from typing import Callable, List, Optional, Any

from .router import RouteDecision


@dataclass(frozen=True)
class HermesRunResult:
    approved: bool
    command: List[str]
    returncode: Optional[int]
    stdout: str
    stderr: str


def build_command(decision: RouteDecision, task: str, hermes_bin: str = "hermes") -> List[str]:
    """Build an argv list; never use a shell or interpolate task text."""
    return [
        hermes_bin,
        "chat",
        "--provider",
        decision.profile.provider,
        "-m",
        decision.profile.model,
        "-Q",
        "-q",
        task,
    ]


def run_approved(
    decision: RouteDecision,
    task: str,
    *,
    approved: bool,
    hermes_bin: Optional[str] = None,
    runner: Callable[..., Any] = subprocess.run,
) -> HermesRunResult:
    """Run a new routed Hermes task only after explicit approval.

    This intentionally starts a bounded new Hermes invocation rather than
    mutating config.yaml or silently changing a live conversation.
    """
    binary = hermes_bin or shutil.which("hermes")
    if not binary:
        raise FileNotFoundError("Hermes executable was not found on PATH")
    command = build_command(decision, task, binary)
    if not approved:
        return HermesRunResult(False, command, None, "", "switch denied; Hermes was not run")
    completed = runner(command, capture_output=True, text=True, check=False)
    return HermesRunResult(
        True,
        command,
        completed.returncode,
        completed.stdout or "",
        completed.stderr or "",
    )
