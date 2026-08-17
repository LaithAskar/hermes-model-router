"""Deterministic, explainable task-to-model routing.

The library intentionally does not call an LLM to classify requests. Users can
provide an explicit task kind or use the conservative keyword classifier. This
keeps routing predictable, private, and cheap.
"""

from dataclasses import dataclass
from enum import Enum
import re
from typing import Iterable, List, Optional, Sequence


class TaskKind(str, Enum):
    CODING = "coding"
    RESEARCH = "research"
    DAILY = "daily"
    HIGH_STAKES = "high_stakes"
    GENERAL = "general"


@dataclass(frozen=True)
class ModelProfile:
    provider: str
    model: str
    strengths: frozenset
    cost_per_million: float = 0.0
    quality_score: float = 0.5
    speed_score: float = 0.5
    privacy: str = "provider"

    def score(self, task: TaskKind, budget: Optional[float] = None) -> float:
        fit = 1.0 if task.value in self.strengths else 0.45
        if task is TaskKind.HIGH_STAKES:
            fit += self.quality_score * 0.8
        else:
            fit += self.quality_score * 0.4 + self.speed_score * 0.2
        if budget is not None and self.cost_per_million > budget:
            fit -= min(1.0, (self.cost_per_million - budget) / max(budget, 0.01))
        return fit


@dataclass(frozen=True)
class RouteDecision:
    task: TaskKind
    profile: ModelProfile
    confidence: float
    reason: str


_KEYWORDS = {
    TaskKind.CODING: {"code", "coding", "bug", "debug", "refactor", "repository", "repo", "test", "implement", "function", "api"},
    TaskKind.RESEARCH: {"research", "compare", "sources", "paper", "citation", "current", "investigate", "web", "market", "literature"},
    TaskKind.HIGH_STAKES: {"security", "legal", "financial", "trade", "medical", "production", "deploy", "credential"},
    TaskKind.DAILY: {"summarize", "summary", "rewrite", "draft", "format", "checklist", "calendar", "email", "routine"},
}


def classify(text: str) -> tuple:
    tokens = set(re.findall(r"[a-z0-9_]+", text.lower()))
    scores = {kind: len(tokens & words) for kind, words in _KEYWORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return TaskKind.GENERAL, 0.35
    ordered = sorted(scores.values(), reverse=True)
    margin = ordered[0] - ordered[1] if len(ordered) > 1 else ordered[0]
    return best, min(0.98, 0.55 + 0.12 * margin)


class Router:
    def __init__(self, profiles: Sequence[ModelProfile]):
        if not profiles:
            raise ValueError("at least one model profile is required")
        self.profiles = tuple(profiles)

    def route(self, text: str, task: Optional[TaskKind] = None, budget: Optional[float] = None) -> RouteDecision:
        if task is None:
            task, confidence = classify(text)
        else:
            confidence = 1.0
        ranked = sorted(self.profiles, key=lambda p: p.score(task, budget), reverse=True)
        chosen = ranked[0]
        reason = "explicit task lane" if confidence == 1.0 else "conservative keyword classification"
        if budget is not None:
            reason += "; cost budget applied"
        return RouteDecision(task, chosen, confidence, reason)


def default_profiles() -> List[ModelProfile]:
    return [
        ModelProfile("openai-codex", "gpt-5.6-sol", frozenset({"coding", "high_stakes", "general"}), 35.0, .98, .72),
        ModelProfile("nous", "google/gemini-3.7-flash", frozenset({"research", "general", "coding"}), 3.75, .88, .90),
        ModelProfile("nous", "deepseek/deepseek-v4-pro-20260813", frozenset({"research", "high_stakes", "general"}), 3.17, .90, .76),
        ModelProfile("nous", "deepseek/deepseek-v4-flash-20260731", frozenset({"daily", "general", "research"}), .22, .72, .98),
        ModelProfile("kimi-coding", "kimi-k3", frozenset({"coding", "research", "general"}), 0.0, .84, .76),
    ]
