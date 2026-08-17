import unittest

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


if __name__ == "__main__":
    unittest.main()
