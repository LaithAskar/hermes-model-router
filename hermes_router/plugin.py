"""Hermes native plugin surfaces for deterministic model routing.

The plugin only proposes routes. It never changes global configuration or an
active session. The returned session command must be approved and executed by
the user or by a separate approval-bound desktop adapter.
"""

import argparse
import base64
import binascii
import json
import shlex
from typing import Any, Dict, Optional, Tuple

from .router import Router, TaskKind, default_profiles


ROUTE_MODEL_SCHEMA = {
    "name": "route_model",
    "description": (
        "Propose a cost-aware Hermes provider/model for a task. This tool is "
        "local and side-effect free: it never switches models. Use it when the "
        "user asks which model to use or wants an explicit routing proposal."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "The task to classify and route."},
            "kind": {
                "type": "string",
                "enum": [kind.value for kind in TaskKind],
                "description": "Optional explicit task lane.",
            },
            "budget": {
                "type": "number",
                "minimum": 0,
                "description": "Optional preferred maximum cost per million output tokens.",
            },
            "current_provider": {"type": "string"},
            "current_model": {"type": "string"},
        },
        "required": ["task"],
    },
}


def build_route_payload(
    task: str,
    *,
    kind: str = "",
    budget: Optional[float] = None,
    current_provider: str = "",
    current_model: str = "",
) -> Dict[str, Any]:
    """Return a JSON-safe, side-effect-free route proposal."""
    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string")
    explicit_kind = None
    if kind:
        try:
            explicit_kind = TaskKind(kind)
        except ValueError as exc:
            raise ValueError(f"unknown task kind: {kind}") from exc
    if budget is not None and budget < 0:
        raise ValueError("budget must be non-negative")

    decision = Router(default_profiles()).route(task.strip(), explicit_kind, budget)
    provider = decision.profile.provider
    model = decision.profile.model
    return {
        "task": decision.task.value,
        "provider": provider,
        "model": model,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "cost_per_million_output": decision.profile.cost_per_million,
        "privacy": decision.profile.privacy,
        "current_provider": current_provider or None,
        "current_model": current_model or None,
        "approval_required": True,
        "switched": False,
        "scope": "session",
        "session_command": f"/model {model} --provider {provider} --session",
        "warning": "Switching models resets prompt-cache continuity for this session.",
    }


def _handle_route_tool(params: Dict[str, Any], **kwargs: Any) -> str:
    del kwargs
    try:
        if not isinstance(params, dict):
            raise ValueError("tool parameters must be an object")
        payload = build_route_payload(
            params.get("task", ""),
            kind=params.get("kind", "") or "",
            budget=params.get("budget"),
            current_provider=params.get("current_provider", "") or "",
            current_model=params.get("current_model", "") or "",
        )
        return json.dumps(payload)
    except (TypeError, ValueError) as exc:
        return json.dumps({"error": str(exc), "approval_required": True, "switched": False})


def _decode_task_b64(value: str) -> str:
    if not value or len(value) > 100_000:
        raise ValueError("--task-b64 must be a bounded base64url value")
    padding = "=" * (-len(value) % 4)
    try:
        raw = base64.b64decode(value + padding, altchars=b"-_", validate=True)
        task = raw.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("--task-b64 must contain valid UTF-8 base64url text") from exc
    if len(task) > 64_000:
        raise ValueError("decoded task exceeds 64,000 characters")
    return task


def _parse_slash_args(raw_args: str) -> Tuple[bool, str, Optional[float], str]:
    try:
        argv = shlex.split(raw_args)
    except ValueError as exc:
        raise ValueError(f"invalid route arguments: {exc}") from exc

    json_mode = False
    kind = ""
    budget = None
    encoded_task = ""
    task_parts = []
    index = 0
    options_done = False
    while index < len(argv):
        token = argv[index]
        if not options_done and token == "--":
            options_done = True
        elif not options_done and token == "--json":
            json_mode = True
        elif not options_done and token == "--kind":
            index += 1
            if index >= len(argv):
                raise ValueError("--kind requires a value")
            kind = argv[index]
        elif not options_done and token == "--budget":
            index += 1
            if index >= len(argv):
                raise ValueError("--budget requires a value")
            try:
                budget = float(argv[index])
            except ValueError as exc:
                raise ValueError("--budget must be a number") from exc
        elif not options_done and token == "--task-b64":
            index += 1
            if index >= len(argv):
                raise ValueError("--task-b64 requires a value")
            encoded_task = argv[index]
        elif not options_done and token.startswith("--"):
            raise ValueError(f"unknown option: {token}")
        else:
            task_parts.append(token)
        index += 1

    if encoded_task and task_parts:
        raise ValueError("use either --task-b64 or plain task text, not both")
    task = _decode_task_b64(encoded_task) if encoded_task else " ".join(task_parts).strip()
    return json_mode, kind, budget, task


def _format_human(payload: Dict[str, Any]) -> str:
    return (
        f"Proposed route: {payload['provider']}/{payload['model']}\n"
        f"Task lane: {payload['task']} (confidence {payload['confidence']:.2f})\n"
        f"Reason: {payload['reason']}\n"
        f"Estimated output cost: ${payload['cost_per_million_output']:.2f}/1M tokens\n\n"
        "Approval required. Review the exact session-only command, then run it yourself:\n"
        f"{payload['session_command']}\n\n"
        "No switch has occurred. Global configuration and Hermes fallback were not changed."
    )


def _handle_route_slash(raw_args: str) -> str:
    try:
        json_mode, kind, budget, task = _parse_slash_args(raw_args)
        if not task:
            return (
                "Usage: /route [--json] [--kind coding|research|daily|high_stakes|general] "
                "[--budget COST] -- <task>"
            )
        payload = build_route_payload(task, kind=kind, budget=budget)
        return json.dumps(payload) if json_mode else _format_human(payload)
    except (TypeError, ValueError) as exc:
        return json.dumps({"error": str(exc), "approval_required": True, "switched": False})


def _setup_cli(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("task", nargs="+", help="Task text to route")
    parser.add_argument("--kind", choices=[kind.value for kind in TaskKind])
    parser.add_argument("--budget", type=float)
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=_handle_cli)


def _handle_cli(args: argparse.Namespace) -> None:
    payload = build_route_payload(
        " ".join(args.task),
        kind=args.kind or "",
        budget=args.budget,
    )
    print(json.dumps(payload, indent=2) if args.json else _format_human(payload))


def register(ctx: Any) -> None:
    """Register the public, non-privileged Hermes plugin surfaces."""
    ctx.register_tool(
        name="route_model",
        toolset="model_router",
        schema=ROUTE_MODEL_SCHEMA,
        handler=_handle_route_tool,
    )
    ctx.register_command(
        "route",
        handler=_handle_route_slash,
        description="Propose a cost-aware session-only model route; never switches automatically.",
        args_hint="[--kind KIND] [--budget COST] -- <task>",
    )
    ctx.register_cli_command(
        name="model-router",
        help="Propose a cost-aware Hermes model route.",
        setup_fn=_setup_cli,
        handler_fn=_handle_cli,
    )
