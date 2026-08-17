import argparse
import json

from .approval import request_approval
from .router import Router, TaskKind, default_profiles


def main() -> None:
    parser = argparse.ArgumentParser(description="Explainably route a Hermes task to a model.")
    parser.add_argument("task", help="Task text")
    parser.add_argument("--kind", choices=[k.value for k in TaskKind])
    parser.add_argument("--budget", type=float, help="Maximum preferred cost per million output tokens")
    parser.add_argument("--current-provider", default="", help="Currently active provider")
    parser.add_argument("--current-model", default="", help="Currently active model")
    parser.add_argument("--ask", action="store_true", help="Ask permission before accepting the proposed route")
    args = parser.parse_args()
    kind = TaskKind(args.kind) if args.kind else None
    decision = Router(default_profiles()).route(args.task, kind, args.budget)
    result = {
        "task": decision.task.value,
        "provider": decision.profile.provider,
        "model": decision.profile.model,
        "confidence": decision.confidence,
        "reason": decision.reason,
    }
    approved = True
    if args.ask:
        approval = request_approval(decision, args.current_provider, args.current_model)
        approved = approval.approved
        result.update({"approved": approved, "message": approval.message})
        if not approved:
            result["provider"] = args.current_provider or None
            result["model"] = args.current_model or None
    print(json.dumps(result, indent=2))
    if args.ask and not approved:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
