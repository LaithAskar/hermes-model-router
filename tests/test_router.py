import unittest

from hermes_router.approval import request_approval
from hermes_router.hermes import run_approved
from hermes_router.router import Router, TaskKind, classify, default_profiles


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.router = Router(default_profiles())

    def test_coding_routes_to_codex(self):
        d = self.router.route("Fix the authentication bug and add tests", TaskKind.CODING)
        self.assertEqual((d.profile.provider, d.profile.model), ("openai-codex", "gpt-5.6-sol"))

    def test_research_routes_to_gemini(self):
        d = self.router.route("Research current papers and compare sources", TaskKind.RESEARCH)
        self.assertEqual(d.profile.model, "google/gemini-3.7-flash")

    def test_daily_prefers_deepseek_flash(self):
        d = self.router.route("Summarize these notes into a checklist", TaskKind.DAILY)
        self.assertEqual(d.profile.model, "deepseek/deepseek-v4-flash-20260731")

    def test_classifier_is_conservative(self):
        kind, confidence = classify("Please fix this repository bug")
        self.assertEqual(kind, TaskKind.CODING)
        self.assertGreater(confidence, 0.5)
        kind, confidence = classify("Tell me something interesting")
        self.assertEqual(kind, TaskKind.GENERAL)
        self.assertLess(confidence, 0.5)

    def test_budget_changes_preference(self):
        d = self.router.route("Do a general task", TaskKind.GENERAL, budget=0.5)
        self.assertNotEqual(d.profile.model, "gpt-5.6-sol")

    def test_approval_accepts_yes(self):
        d = self.router.route("Fix a bug", TaskKind.CODING)
        result = request_approval(d, "nous", "google/gemini-3.7-flash", input_fn=lambda _: "yes")
        self.assertTrue(result.approved)
        self.assertIn("switch approved", result.message)

    def test_approval_defaults_to_deny(self):
        d = self.router.route("Research sources", TaskKind.RESEARCH)
        result = request_approval(d, "openai-codex", "gpt-5.6-sol", input_fn=lambda _: "")
        self.assertFalse(result.approved)
        self.assertIn("staying on", result.message)

    def test_denied_route_never_runs_hermes(self):
        d = self.router.route("Fix a bug", TaskKind.CODING)
        calls = []
        result = run_approved(d, "Fix a bug", approved=False, hermes_bin="/usr/bin/hermes", runner=lambda *a, **k: calls.append(a))
        self.assertFalse(result.approved)
        self.assertEqual(calls, [])

    def test_approved_route_uses_argv_without_shell(self):
        d = self.router.route("Fix a bug; do not execute shell", TaskKind.CODING)
        seen = {}

        class Completed:
            returncode = 0
            stdout = "ok"
            stderr = ""

        def fake_runner(command, **kwargs):
            seen["command"] = command
            seen["kwargs"] = kwargs
            return Completed()

        result = run_approved(d, "Fix a bug; do not execute shell", approved=True, hermes_bin="/usr/bin/hermes", runner=fake_runner)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(seen["command"][0], "/usr/bin/hermes")
        self.assertFalse(seen["kwargs"].get("shell", False))


if __name__ == "__main__":
    unittest.main()
