import argparse
import json

from .router import Router, TaskKind, default_profiles


def main() -> None:
    parser = argparse.ArgumentParser(description="Explainably route a Hermes task to a model.")
    parser.add_argument("task", help="Task text")
    parser.add_argument("--kind", choices=[k.value for k in TaskKind])
    parser.add_argument("--budget", type=float, help="Maximum preferred cost per million output tokens")
    args = parser.parse_args()
    kind = TaskKind(args.kind) if args.kind else None
    decision = Router(default_profiles()).route(args.task, kind, args.budget)
    print(json.dumps({
        "task": decision.task.value,
        "provider": decision.profile.provider,
        "model": decision.profile.model,
        "confidence": decision.confidence,
        "reason": decision.reason,
    }, indent=2))


if __name__ == "__main__":
    main()
