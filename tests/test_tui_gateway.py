import json
import unittest

from hermes_router.session_switch import SessionSwitchError
from hermes_router.tui_gateway import TuiGatewayTransport


class FakeSocket:
    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []

    def send(self, raw):
        self.sent.append(json.loads(raw))

    def recv(self, timeout=None):
        if not self.replies:
            raise TimeoutError()
        reply = dict(self.replies.pop(0))
        if reply.get("id") == "CURRENT":
            reply["id"] = self.sent[-1]["id"]
        return json.dumps(reply)


class TuiGatewayTransportTests(unittest.TestCase):
    def test_status_parses_provider_model_and_busy_state(self):
        socket = FakeSocket([{
            "id": "CURRENT",
            "result": {"output": "Hermes TUI Status\n\nSession ID: s1\nModel: gpt-5.6-sol (openai-codex)\nAgent Running: No"},
        }])
        snapshot = TuiGatewayTransport(socket).get_session("s1")
        self.assertEqual((snapshot.provider, snapshot.model), ("openai-codex", "gpt-5.6-sol"))
        self.assertFalse(snapshot.running)
        self.assertEqual(socket.sent[0]["method"], "session.status")

    def test_switch_uses_native_session_scoped_slash_command(self):
        socket = FakeSocket([{"id": "CURRENT", "result": {"output": "switched"}}])
        TuiGatewayTransport(socket).switch_session_model("s1", "openai-codex", "gpt-5.6-sol")
        self.assertEqual(socket.sent[0]["method"], "slash.exec")
        self.assertEqual(
            socket.sent[0]["params"]["command"],
            "/model gpt-5.6-sol --provider openai-codex --session",
        )

    def test_rpc_error_is_fail_closed(self):
        socket = FakeSocket([{"id": "CURRENT", "error": {"message": "not active"}}])
        with self.assertRaisesRegex(SessionSwitchError, "not active"):
            TuiGatewayTransport(socket).get_session("s1")

    def test_incomplete_status_is_rejected(self):
        socket = FakeSocket([{"id": "CURRENT", "result": {"output": "unknown"}}])
        with self.assertRaisesRegex(SessionSwitchError, "incomplete"):
            TuiGatewayTransport(socket).get_session("s1")

    def test_busy_output_is_rejected(self):
        socket = FakeSocket([{"id": "CURRENT", "result": {"output": "session busy — interrupt first"}}])
        with self.assertRaisesRegex(SessionSwitchError, "busy"):
            TuiGatewayTransport(socket).switch_session_model("s1", "nous", "google/gemini-3.7-flash")

    def test_option_injection_in_provider_or_model_is_rejected(self):
        socket = FakeSocket([])
        transport = TuiGatewayTransport(socket)
        with self.assertRaisesRegex(ValueError, "unsafe provider"):
            transport.switch_session_model("s1", "nous --global", "safe-model")
        with self.assertRaisesRegex(ValueError, "unsafe model"):
            transport.switch_session_model("s1", "nous", "safe-model --global")
        self.assertEqual(socket.sent, [])


if __name__ == "__main__":
    unittest.main()
