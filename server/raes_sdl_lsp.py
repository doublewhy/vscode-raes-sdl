#!/usr/bin/env python3
"""Prototype stdio language server that bridges editors to ``raes.language_service``.

Features: diagnostics (on open, on save, and debounced on change), completion and
go-to-definition. Formatting is deliberately not offered: ``language_format`` drops YAML
comments and rewrites shorthand, so a format-on-save integration would be destructive.

Completion items come from ``language_completions`` unchanged, with one syntactic filter:
field-name items are dropped when the cursor is in a value position (after ``key:`` or in a
flow sequence), because the helper returns a section's field list at any depth below it.
Reference candidates are never filtered, so helper mismatches such as issue 1339 stay visible.

The server passes the open document's text to the in-process rae helpers. It does not launch
scenarios, read other files, or use the network. It depends only on the Python standard
library and on the ``raes`` distribution installed in the interpreter that runs it, so the
selected interpreter decides the SDL version the editor follows.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any, BinaryIO

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sdl_cursor import cursor_context, word_at  # noqa: E402

BRIDGE_VERSION = "0.0.1"
DEBOUNCE_SECONDS = 0.4
NO_RANGE_NOTE = " (raes reported no source location)"
STALE_NOTE = " (from the last parsable version)"
SEVERITY = {"error": 1, "warning": 2, "information": 3, "info": 3, "hint": 4}
COMPLETION_KIND = {"field": 5, "reference": 18}

try:
    import raes
    from raes import language_service
except Exception as exc:  # report through LSP instead of crashing the client
    raes = None
    language_service = None
    IMPORT_ERROR: str | None = f"{type(exc).__name__}: {exc}"
else:
    IMPORT_ERROR = None


def read_message(stream: BinaryIO) -> dict[str, Any] | None:
    """Read one base-protocol message; None at end of stream."""
    length = None
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        name, _, value = line.decode("ascii").partition(":")
        if name.strip().lower() == "content-length":
            length = int(value.strip())
    if length is None:
        return None
    return json.loads(stream.read(length).decode("utf-8"))


def lsp_position(location: dict[str, int]) -> dict[str, int]:
    """Convert a rae 1-based line/column to an LSP 0-based position."""
    return {"line": max(location.get("line", 1) - 1, 0), "character": max(location.get("column", 1) - 1, 0)}


def lsp_range(item_range: dict[str, Any] | None) -> dict[str, Any]:
    if not item_range:
        origin = {"line": 0, "character": 0}
        return {"start": origin, "end": origin}
    return {"start": lsp_position(item_range["start"]), "end": lsp_position(item_range["end"])}


def to_lsp_diagnostic(item: dict[str, Any], uri: str) -> dict[str, Any]:
    """Translate one rae diagnostic record; record-level fields are kept, none are invented."""
    message = item.get("message", "")
    if "range" not in item:
        message += NO_RANGE_NOTE
    diagnostic: dict[str, Any] = {
        "range": lsp_range(item.get("range")),
        "severity": SEVERITY.get(str(item.get("severity", "error")).lower(), 1),
        "source": "raes",
        "message": message,
    }
    if item.get("code"):
        diagnostic["code"] = item["code"]
    related = [
        {"location": {"uri": uri, "range": lsp_range(entry.get("range"))}, "message": entry.get("message", "")}
        for entry in item.get("related", [])
    ]
    if related:
        diagnostic["relatedInformation"] = related
    return diagnostic


class Document:
    def __init__(self, text: str, version: int | None) -> None:
        # One tuple, replaced as a whole, so a debounce thread never pairs one edit's text
        # with another edit's version.
        self.snapshot: tuple[str, int | None] = (text, version)
        self.last_completable: str | None = None
        self.timer: threading.Timer | None = None

    @property
    def text(self) -> str:
        return self.snapshot[0]


class Server:
    def __init__(self, reader: BinaryIO, writer: BinaryIO, *, debounce: float = DEBOUNCE_SECONDS) -> None:
        self.reader = reader
        self.writer = writer
        self.debounce = debounce
        self.documents: dict[str, Document] = {}
        self.write_lock = threading.Lock()
        self.helper_lock = threading.Lock()
        self.shutdown_requested = False

    # -- transport -------------------------------------------------------------------------
    def send(self, message: dict[str, Any]) -> None:
        body = json.dumps(message).encode("utf-8")
        with self.write_lock:
            self.writer.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
            self.writer.flush()

    def notify(self, method: str, params: Any) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def serve(self) -> int:
        while True:
            message = read_message(self.reader)
            if message is None:
                return 0 if self.shutdown_requested else 1
            if message.get("method") == "exit":
                return 0 if self.shutdown_requested else 1
            self.dispatch(message)

    def dispatch(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        handler = self.REQUESTS.get(method) if "id" in message else self.NOTIFICATIONS.get(method)
        if "id" not in message:
            if handler is not None:
                handler(self, message.get("params") or {})
            return
        if handler is None:
            self.send({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": f"{method}"}})
            return
        try:
            result = handler(self, message.get("params") or {})
        except Exception as exc:  # keep the session alive; surface the failure to the client
            self.send({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32603, "message": repr(exc)}})
            return
        self.send({"jsonrpc": "2.0", "id": message["id"], "result": result})

    # -- lifecycle -------------------------------------------------------------------------
    def initialize(self, _params: dict[str, Any]) -> dict[str, Any]:
        raes_version = getattr(raes, "__version__", "unknown") if raes is not None else "unavailable"
        return {
            "capabilities": {
                "textDocumentSync": {"openClose": True, "change": 1, "save": {"includeText": False}},
                "completionProvider": {"triggerCharacters": [" ", "[", ",", "-"]},
                "definitionProvider": True,
            },
            "serverInfo": {"name": "raes-sdl-bridge", "version": f"{BRIDGE_VERSION}; raes {raes_version}"},
        }

    def initialized(self, _params: dict[str, Any]) -> None:
        if IMPORT_ERROR is not None:
            self.notify(
                "window/showMessage",
                {
                    "type": 1,
                    "message": (
                        f"OpenRAE SDL: raes is not importable from {sys.executable} ({IMPORT_ERROR}). "
                        "Set openraeSdl.python to an interpreter with raes installed."
                    ),
                },
            )

    def shutdown(self, _params: dict[str, Any]) -> None:
        self.shutdown_requested = True
        for document in self.documents.values():
            if document.timer is not None:
                document.timer.cancel()

    # -- documents -------------------------------------------------------------------------
    def did_open(self, params: dict[str, Any]) -> None:
        item = params["textDocument"]
        self.documents[item["uri"]] = Document(item["text"], item.get("version"))
        self.publish(item["uri"])

    def did_change(self, params: dict[str, Any]) -> None:
        uri = params["textDocument"]["uri"]
        document = self.documents.get(uri)
        if document is None or not params.get("contentChanges"):
            return
        document.snapshot = (params["contentChanges"][-1]["text"], params["textDocument"].get("version"))
        if document.timer is not None:
            document.timer.cancel()
        document.timer = threading.Timer(self.debounce, self.publish, args=(uri,))
        document.timer.daemon = True
        document.timer.start()

    def did_save(self, params: dict[str, Any]) -> None:
        self.publish(params["textDocument"]["uri"])

    def did_close(self, params: dict[str, Any]) -> None:
        uri = params["textDocument"]["uri"]
        document = self.documents.pop(uri, None)
        if document is not None and document.timer is not None:
            document.timer.cancel()
        self.notify("textDocument/publishDiagnostics", {"uri": uri, "diagnostics": []})

    def publish(self, uri: str) -> None:
        document = self.documents.get(uri)
        if document is None or language_service is None:
            return
        text, version = document.snapshot
        with self.helper_lock:
            result = language_service.language_diagnostics(text)
            if language_service.language_completions(text, cursor_path="").get("status") == "ok":
                document.last_completable = text
        if self.documents.get(uri) is not document or document.snapshot[1] != version:
            return  # a newer edit arrived; its own timer will publish
        diagnostics = [to_lsp_diagnostic(item, uri) for item in result.get("diagnostics", [])]
        self.notify("textDocument/publishDiagnostics", {"uri": uri, "version": version, "diagnostics": diagnostics})

    # -- language features -----------------------------------------------------------------
    def completion(self, params: dict[str, Any]) -> dict[str, Any]:
        empty = {"isIncomplete": False, "items": []}
        document = self.documents.get(params["textDocument"]["uri"])
        if document is None or language_service is None:
            return empty
        position = params["position"]
        text = document.text
        context = cursor_context(text, position["line"], position["character"])
        if context is None:
            return empty
        stale = False
        with self.helper_lock:
            result = language_service.language_completions(text, cursor_path=context.path)
            if result.get("status") == "ok":
                document.last_completable = text
            elif document.last_completable is not None:
                result = language_service.language_completions(document.last_completable, cursor_path=context.path)
                stale = True
        if result.get("status") != "ok":
            return empty
        items = [
            {
                "label": item["label"],
                "kind": COMPLETION_KIND.get(item.get("kind", ""), 1),
                "detail": item.get("detail", "") + (STALE_NOTE if stale else ""),
                "insertText": item.get("insert_text", item["label"]),
            }
            for item in result.get("items", [])
            if not (context.value_position and item.get("kind") == "field")
        ]
        return {"isIncomplete": False, "items": items}

    def definition(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        uri = params["textDocument"]["uri"]
        document = self.documents.get(uri)
        if document is None or language_service is None:
            return []
        position = params["position"]
        text = document.text
        symbol = word_at(text, position["line"], position["character"])
        if not symbol:
            return []
        with self.helper_lock:
            result = language_service.language_references(text, symbol)
        if result.get("status") != "ok":
            return []
        return [{"uri": uri, "range": lsp_range(item.get("range"))} for item in result.get("definitions", [])]

    REQUESTS = {
        "initialize": initialize,
        "shutdown": shutdown,
        "textDocument/completion": completion,
        "textDocument/definition": definition,
    }
    NOTIFICATIONS = {
        "initialized": initialized,
        "textDocument/didOpen": did_open,
        "textDocument/didChange": did_change,
        "textDocument/didSave": did_save,
        "textDocument/didClose": did_close,
    }


def main() -> int:
    return Server(sys.stdin.buffer, sys.stdout.buffer).serve()


if __name__ == "__main__":
    sys.exit(main())
