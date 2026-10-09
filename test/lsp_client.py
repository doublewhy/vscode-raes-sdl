"""Minimal stdio LSP client used by the tests and evidence scripts to drive language servers headlessly."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from collections.abc import Callable
from typing import Any


class LspClient:
    def __init__(
        self,
        command: list[str],
        settings: dict[str, Any] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.settings = settings or {}
        self.inbox: queue.Queue[dict[str, Any]] = queue.Queue()
        self.notifications: list[dict[str, Any]] = []
        self.stderr: list[str] = []
        self.next_id = 0
        self.lock = threading.Lock()
        self.proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=None if env is None else {**os.environ, **env},
        )
        threading.Thread(target=self._read_loop, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _drain_stderr(self) -> None:
        for line in self.proc.stderr:
            self.stderr.append(line.decode("utf-8", "replace"))

    def _read_loop(self) -> None:
        stream = self.proc.stdout
        while True:
            headers: dict[str, str] = {}
            while True:
                line = stream.readline()
                if not line:
                    return
                text = line.decode("ascii").strip()
                if not text:
                    break
                name, _, value = text.partition(":")
                headers[name.strip().lower()] = value.strip()
            self.inbox.put(json.loads(stream.read(int(headers["content-length"]))))

    def _write(self, message: dict[str, Any]) -> None:
        body = json.dumps(message).encode("utf-8")
        with self.lock:
            self.proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
            self.proc.stdin.flush()

    def notify(self, method: str, params: Any) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _answer_server_request(self, message: dict[str, Any]) -> None:
        result: Any = None
        if message["method"] == "workspace/configuration":
            result = []
            for item in message["params"]["items"]:
                value: Any = self.settings
                for part in item.get("section", "").split(".") if item.get("section") else []:
                    value = value.get(part) if isinstance(value, dict) else None
                result.append(value)
        self._write({"jsonrpc": "2.0", "id": message["id"], "result": result})

    def pump(self, timeout: float) -> dict[str, Any] | None:
        try:
            message = self.inbox.get(timeout=timeout)
        except queue.Empty:
            return None
        if "method" in message and "id" in message:
            self._answer_server_request(message)
        elif "method" in message:
            self.notifications.append(message)
        return message

    def request(self, method: str, params: Any, timeout: float = 30.0) -> Any:
        self.next_id += 1
        request_id = self.next_id
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self.pump(0.1)
            if message and message.get("id") == request_id and "method" not in message:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result")
        raise TimeoutError(method)

    def settle(self, quiet: float = 1.5, limit: float = 30.0) -> None:
        """Pump messages until the server has been quiet for `quiet` seconds."""
        deadline = time.monotonic() + limit
        last = time.monotonic()
        while time.monotonic() < deadline and time.monotonic() - last < quiet:
            if self.pump(0.1) is not None:
                last = time.monotonic()

    def diagnostics_for(self, uri: str) -> list[dict[str, Any]] | None:
        found = None
        for message in self.notifications:
            if message["method"] == "textDocument/publishDiagnostics" and message["params"]["uri"] == uri:
                found = message["params"]["diagnostics"]
        return found

    def wait_for(self, predicate: Callable[[dict[str, Any]], bool], timeout: float = 30.0) -> dict[str, Any]:
        """Return the first recorded or future notification that satisfies `predicate`."""
        seen = 0
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for message in self.notifications[seen:]:
                if predicate(message):
                    return message
            seen = len(self.notifications)
            self.pump(0.1)
        raise TimeoutError("notification not received")

    def close(self) -> int | None:
        try:
            self.request("shutdown", None, timeout=5)
            self.notify("exit", None)
        except (OSError, RuntimeError, TimeoutError):
            pass
        try:
            code = self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
            code = None
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                stream.close()
            except OSError:
                pass
        return code
