import unittest

from hermes_router.approval import request_approval
from hermes_router.router import Router, TaskKind, default_profiles
from hermes_router.session_switch import (
    SessionSnapshot,
    SessionSwitchApproval,
    SessionSwitchError,
    switch_approved_session,
)


class FakeTransport:
    def __init__(self, snapshots, switch_response=None):
        self.snapshots = list(snapshots)
        self.switch_response = switch_response or {"result": {"output": "switched"}}
        self.calls = []

    def get_session(self, session_id):
        self.calls.append(("status", session_id))
        if not self.snapshots:
            raise AssertionError("unexpected status read")
        return self.snapshots.pop(0)

    def switch_session_model(self, session_id, provider, model):
        self.calls.append(("switch", session_id, provider, model))
        return self.switch_response


class SessionSwitchTests(unittest.TestCase):
    def setUp(self):
        self.decision = Router(default_profiles()).route("Fix a bug", TaskKind.CODING)
        self.before = SessionSnapshot("session-1", "nous", "google/gemini-3.7-flash", False, True)

    def approval(self, approved=True):
        route_approval = request_approval(
            self.decision,
            self.before.provider,
            self.before.model,
            input_fn=lambda _: "yes" if approved else "",
        )
        return SessionSwitchApproval(route_approval, self.before)

    def test_approved_switch_revalidates_and_verifies(self):
        after = SessionSnapshot("session-1", "openai-codex", "gpt-5.6-sol", False, True)
        transport = FakeTransport([self.before, after])
        result = switch_approved_session(self.decision, self.approval(), transport)
        self.assertTrue(result.switched)
        self.assertEqual(
            transport.calls,
            [
                ("status", "session-1"),
                ("switch", "session-1", "openai-codex", "gpt-5.6-sol"),
                ("status", "session-1"),
            ],
        )

    def test_denial_makes_no_transport_calls(self):
        transport = FakeTransport([])
        result = switch_approved_session(self.decision, self.approval(False), transport)
        self.assertFalse(result.switched)
        self.assertEqual(transport.calls, [])

    def test_stale_route_is_rejected_before_switch(self):
        stale = SessionSnapshot("session-1", "kimi-coding", "kimi-k3", False, True)
        transport = FakeTransport([stale])
        with self.assertRaisesRegex(SessionSwitchError, "stale"):
            switch_approved_session(self.decision, self.approval(), transport)
        self.assertNotIn("switch", [call[0] for call in transport.calls])

    def test_busy_session_is_rejected(self):
        busy = SessionSnapshot("session-1", self.before.provider, self.before.model, True, True)
        transport = FakeTransport([busy])
        with self.assertRaisesRegex(SessionSwitchError, "busy"):
            switch_approved_session(self.decision, self.approval(), transport)

    def test_inactive_session_is_rejected(self):
        inactive = SessionSnapshot("session-1", self.before.provider, self.before.model, False, False)
        transport = FakeTransport([inactive])
        with self.assertRaisesRegex(SessionSwitchError, "active"):
            switch_approved_session(self.decision, self.approval(), transport)

    def test_rpc_failure_is_fail_closed(self):
        transport = FakeTransport([self.before], {"error": {"message": "model unavailable"}})
        with self.assertRaisesRegex(SessionSwitchError, "model unavailable"):
            switch_approved_session(self.decision, self.approval(), transport)

    def test_post_switch_mismatch_is_failure(self):
        transport = FakeTransport([self.before, self.before])
        with self.assertRaisesRegex(SessionSwitchError, "verification"):
            switch_approved_session(self.decision, self.approval(), transport)

    def test_approval_is_bound_to_exact_session(self):
        other = SessionSnapshot("session-2", self.before.provider, self.before.model, False, True)
        approval = SessionSwitchApproval(self.approval().route, other)
        transport = FakeTransport([self.before])
        with self.assertRaisesRegex(SessionSwitchError, "session"):
            switch_approved_session(self.decision, approval, transport, session_id="session-1")


if __name__ == "__main__":
    unittest.main()
