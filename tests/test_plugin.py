import base64
import json
import unittest
from pathlib import Path

from hermes_router.plugin import build_route_payload, register


class FakeContext:
    def __init__(self):
        self.tools = {}
        self.commands = {}
        self.cli_commands = {}

    def register_tool(self, *, name, toolset, schema, handler, **kwargs):
        self.tools[name] = {
            "toolset": toolset,
            "schema": schema,
            "handler": handler,
            **kwargs,
        }

    def register_command(self, name, *, handler, description="", args_hint=""):
        self.commands[name] = {
            "handler": handler,
            "description": description,
            "args_hint": args_hint,
        }

    def register_cli_command(self, *, name, help, setup_fn, handler_fn):
        self.cli_commands[name] = {
            "help": help,
            "setup_fn": setup_fn,
            "handler_fn": handler_fn,
        }


class PluginTests(unittest.TestCase):
    def test_distribution_uses_module_entrypoint_and_unified_desktop_layout(self):
        root = Path(__file__).resolve().parents[1]
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('hermes-model-router = "hermes_router.plugin"', pyproject)
        self.assertNotIn('hermes-model-router = "hermes_router.plugin:register"', pyproject)
        self.assertTrue((root / "desktop" / "plugin.js").is_file())

    def test_registers_tool_slash_and_cli_surfaces(self):
        ctx = FakeContext()
        register(ctx)
        self.assertIn("route_model", ctx.tools)
        self.assertIn("route", ctx.commands)
        self.assertIn("model-router", ctx.cli_commands)
        self.assertEqual(ctx.tools["route_model"]["toolset"], "model_router")

    def test_route_tool_returns_json_without_switching(self):
        ctx = FakeContext()
        register(ctx)
        raw = ctx.tools["route_model"]["handler"](
            {
                "task": "Fix the authentication bug and add tests",
                "kind": "coding",
                "current_provider": "nous",
                "current_model": "openai/gpt-5.6-sol-pro",
            }
        )
        result = json.loads(raw)
        self.assertEqual(result["provider"], "openai-codex")
        self.assertEqual(result["model"], "gpt-5.6-sol")
        self.assertTrue(result["approval_required"])
        self.assertFalse(result["switched"])
        self.assertNotIn("--global", result["session_command"])
        self.assertTrue(result["session_command"].endswith("--session"))

    def test_slash_json_is_machine_readable_and_side_effect_free(self):
        ctx = FakeContext()
        register(ctx)
        raw = ctx.commands["route"]["handler"](
            "--json --kind research -- Research current papers and compare sources"
        )
        result = json.loads(raw)
        self.assertEqual(result["task"], "research")
        self.assertTrue(result["approval_required"])
        self.assertFalse(result["switched"])

    def test_slash_accepts_base64url_task_for_desktop_transport(self):
        ctx = FakeContext()
        register(ctx)
        task = "Fix quotes: 'single' and \"double\"\nthen add tests ✓"
        encoded = base64.urlsafe_b64encode(task.encode("utf-8")).decode("ascii").rstrip("=")
        raw = ctx.commands["route"]["handler"](
            f"--json --kind coding --task-b64 {encoded}"
        )
        result = json.loads(raw)
        self.assertEqual(result["task"], "coding")
        self.assertFalse(result["switched"])
        self.assertNotIn("error", result)

    def test_slash_rejects_invalid_base64url_task(self):
        ctx = FakeContext()
        register(ctx)
        raw = ctx.commands["route"]["handler"]("--json --task-b64 !!!")
        result = json.loads(raw)
        self.assertIn("error", result)
        self.assertFalse(result["switched"])

    def test_slash_human_output_requires_explicit_native_command(self):
        ctx = FakeContext()
        register(ctx)
        result = ctx.commands["route"]["handler"]("Fix the repository bug")
        self.assertIn("Approval required", result)
        self.assertIn("/model", result)
        self.assertIn("--session", result)
        self.assertNotIn("--global", result)

    def test_invalid_kind_fails_closed(self):
        with self.assertRaises(ValueError):
            build_route_payload("Do something", kind="made-up")


if __name__ == "__main__":
    unittest.main()
