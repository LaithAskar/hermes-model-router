import re
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1] / "desktop" / "plugin.js"


class DesktopPluginContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PLUGIN.read_text(encoding="utf-8")

    def test_uses_only_supported_imports(self):
        imports = re.findall(r"from\s+['\"]([^'\"]+)['\"]", self.source)
        self.assertTrue(imports)
        self.assertTrue(set(imports) <= {"@hermes/plugin-sdk", "react", "react/jsx-runtime"})

    def test_routes_through_native_plugin_with_safe_task_transport(self):
        self.assertIn("/route --json", self.source)
        self.assertIn("--task-b64", self.source)
        self.assertIn("encodeTask(task.trim())", self.source)

    def test_switch_is_explicit_session_only_and_never_global(self):
        self.assertIn("Approve and switch this session", self.source)
        self.assertIn("`/model ${proposal.model} --provider ${proposal.provider} --session`", self.source)
        self.assertNotRegex(self.source, r"command\s*=.*--global")

    def test_revalidates_before_and_after_switch(self):
        self.assertIn("host.state.focusedSessionId", self.source)
        self.assertGreaterEqual(self.source.count("host.state.focusedSessionId.get()"), 2)
        self.assertGreaterEqual(self.source.count("readSession(sessionId)"), 3)
        self.assertIn("Approval is stale: the active session changed.", self.source)
        self.assertIn("Approval is stale: the active provider or model changed.", self.source)
        self.assertIn("Post-switch verification failed.", self.source)

    def test_does_not_submit_task_or_mutate_config(self):
        self.assertIn("Your task was not sent automatically.", self.source)
        self.assertNotIn("config.set", self.source)
        self.assertNotIn("config.update", self.source)


if __name__ == "__main__":
    unittest.main()
