"""JSON-RPC transport for Hermes' authenticated TUI gateway WebSocket."""

import json
import re
import time
from typing import Any, Callable, Optional

from .session_switch import SessionSnapshot, SessionSwitchError


_STATUS_MODEL_RE = re.compile(r"^Model:\s*(.+?)\s*\(([^()]+)\)\s*$", re.MULTILINE)
_STATUS_RUNNING_RE = re.compile(r"^Agent Running:\s*(Yes|No)\s*$", re.MULTILINE | re.IGNORECASE)


class TuiGatewayTransport:
    """Small synchronous adapter over an already-authorized WebSocket.

    A caller supplies a connected socket-like object with ``send``, ``recv``,
    and optional ``close`` methods. Authentication and endpoint discovery stay
    outside this library so credentials are never read from Hermes config.
    """

    def __init__(self, socket: Any, *, timeout: float = 15.0, clock: Callable[[], float] = time.monotonic):
        self.socket = socket
        self.timeout = timeout
        self.clock = clock
        self._request_id = 0

    def _rpc(self, method: str, params: dict) -> dict:
        self._request_id += 1
        request_id = f"hmr-{self._request_id}"
        self.socket.send(json.dumps({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }))
        deadline = self.clock() + self.timeout
        while self.clock() < deadline:
            try:
                raw = self.socket.recv(timeout=max(0.01, deadline - self.clock()))
            except TimeoutError:
                continue
            try:
                message = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if message.get("id") == request_id:
                return message
        raise SessionSwitchError(f"Hermes RPC timed out: {method}")

    def get_session(self, session_id: str) -> SessionSnapshot:
        response = self._rpc("session.status", {"session_id": session_id})
        if response.get("error"):
            raise SessionSwitchError(_error_message(response))
        output = str((response.get("result") or {}).get("output") or "")
        model_match = _STATUS_MODEL_RE.search(output)
        running_match = _STATUS_RUNNING_RE.search(output)
        if not model_match or not running_match:
            raise SessionSwitchError("Hermes returned an incomplete session status")
        model = model_match.group(1).strip()
        provider = model_match.group(2).strip()
        return SessionSnapshot(
            session_id=session_id,
            provider=provider,
            model=model,
            running=running_match.group(1).lower() == "yes",
            active=True,
        )

    def switch_session_model(self, session_id: str, provider: str, model: str) -> dict:
        response = self._rpc(
            "slash.exec",
            {
                "session_id": session_id,
                "command": f"/model {model} --provider {provider} --session",
            },
        )
        if response.get("error"):
            raise SessionSwitchError(_error_message(response))
        result = response.get("result") or {}
        if result.get("confirm_required"):
            raise SessionSwitchError("Hermes requested an additional model confirmation")
        output = str(result.get("output") or "")
        if "session busy" in output.lower():
            raise SessionSwitchError(output)
        return response

    def close(self) -> None:
        close = getattr(self.socket, "close", None)
        if callable(close):
            close()


def _error_message(response: dict) -> str:
    error = response.get("error") or {}
    if isinstance(error, dict):
        return str(error.get("message") or "Hermes RPC failed")
    return str(error)
