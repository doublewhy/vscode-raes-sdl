"""Drive the bridge over stdio exactly as an editor client would.

Set RAES_PYTHON to an interpreter in which ``raes`` is importable (for example the
``implementations/python/.venv/bin/python`` of an OpenRAE/rae checkout, or a virtual
environment with ``pip install raes``). Tests that need raes are skipped otherwise.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lsp_client import LspClient  # noqa: E402
from raising_helpers import MARKER as RAISE_MARKER  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server" / "raes_sdl_lsp.py"
RAISING_LAUNCHER = ROOT / "test" / "raising_helpers.py"
PYTHON = os.environ.get("RAES_PYTHON", sys.executable)
NO_RANGE_NOTE = "(raes reported no source location)"
STALE_NOTE = "(from the last parsable version)"

BLOCK_NODE = """\
name: demo
features:
  app: {type: service, source: webapp}
nodes:
  web:
    type: compute
    os: linux
    resources: {ram: 2 GiB, cpu: 1}
    features: [app]
"""

PARTICIPANTS = """\
name: audit
entities:
  team: {role: red}
agents:
  one: {affiliations: [team]}
  two: {affiliations: [team]}
propositions:
  ok:
    description: declared state
    subjects: [agents.one]
    basis: declared_state
    predicate:
      kind: boolean
      property: ready
      semantic_ref: urn:raes:declared-property:ready
      operator: equals
      expected: true
assertions:
  done: {proposition: ok, role: postcondition, polarity: positive}
relationships:
  pair:
    type: participant
    source: agents.one
    target: agents.two
    participant: {kind: cooperation}
"""


def _raes_available() -> bool:
    probe = subprocess.run([PYTHON, "-c", "import raes.language_service"], capture_output=True, check=False)
    return probe.returncode == 0


def _start(env: dict[str, str] | None = None, script: Path = SERVER) -> tuple[LspClient, dict]:
    client = LspClient([PYTHON, str(script)], env=env)
    result = client.request("initialize", {"processId": None, "rootUri": None, "capabilities": {}}, timeout=60)
    client.notify("initialized", {})
    return client, result


class _Session:
    """One server process per test class, driven through the helpers below."""

    script = SERVER
    client: LspClient
    init: dict
    counter: int

    @classmethod
    def setUpClass(cls) -> None:
        cls.client, cls.init = _start(script=cls.script)
        cls.counter = 0

    @classmethod
    def tearDownClass(cls) -> None:
        cls.exit_code = cls.client.close()

    def _uri(self) -> str:
        type(self).counter += 1
        return f"file:///workspace/doc{self.counter}.sdl.yaml"

    def _diagnostics(self, uri: str, version: int) -> list[dict]:
        message = self.client.wait_for(
            lambda m: m["method"] == "textDocument/publishDiagnostics"
            and m["params"]["uri"] == uri
            and m["params"].get("version") == version
        )
        return message["params"]["diagnostics"]

    def open(self, text: str) -> tuple[str, list[dict]]:
        uri = self._uri()
        self.client.notify(
            "textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": "openrae-sdl", "version": 1, "text": text}}
        )
        return uri, self._diagnostics(uri, 1)

    def change(self, uri: str, text: str, version: int) -> list[dict]:
        self.client.notify(
            "textDocument/didChange",
            {"textDocument": {"uri": uri, "version": version}, "contentChanges": [{"text": text}]},
        )
        return self._diagnostics(uri, version)

    def complete(self, uri: str, line: int, character: int) -> list[dict]:
        result = self.client.request(
            "textDocument/completion", {"textDocument": {"uri": uri}, "position": {"line": line, "character": character}}
        )
        return result["items"]


@unittest.skipUnless(_raes_available(), f"raes is not importable from {PYTHON}")
class BridgeTest(_Session, unittest.TestCase):
    def test_initialize_reports_raes_version_and_omits_formatting(self) -> None:
        self.assertIn("; raes ", self.init["serverInfo"]["version"])
        self.assertNotIn("unavailable", self.init["serverInfo"]["version"])
        capabilities = self.init["capabilities"]
        self.assertTrue(capabilities["definitionProvider"])
        self.assertIn("completionProvider", capabilities)
        self.assertNotIn("documentFormattingProvider", capabilities)

    def test_valid_document_publishes_no_diagnostics(self) -> None:
        _, diagnostics = self.open(BLOCK_NODE)
        self.assertEqual(diagnostics, [])

    def test_structural_error_keeps_the_rae_source_range(self) -> None:
        text = BLOCK_NODE.replace("    features: [app]\n", "    features: [app]\n    colour: blue\n")
        _, diagnostics = self.open(text)
        self.assertEqual(len(diagnostics), 1)
        line = text.split("\n").index("    colour: blue")
        # rae ranges an unknown field on its value, not its key; the bridge converts it unchanged.
        self.assertEqual(diagnostics[0]["range"]["start"], {"line": line, "character": len("    colour: ")})
        self.assertEqual(diagnostics[0]["code"], "sdl.model.invalid")
        self.assertEqual(diagnostics[0]["source"], "raes")

    def test_semantic_error_has_no_source_range(self) -> None:
        _, diagnostics = self.open(BLOCK_NODE.replace("features: [app]", "features: [missing]"))
        self.assertTrue(diagnostics)
        for diagnostic in diagnostics:
            self.assertEqual(diagnostic["code"], "sdl.semantic")
            self.assertEqual(diagnostic["range"]["start"], {"line": 0, "character": 0})
            self.assertIn(NO_RANGE_NOTE, diagnostic["message"])

    def test_duplicate_key_carries_related_information(self) -> None:
        _, diagnostics = self.open("name: demo\nname: again\n")
        self.assertEqual(diagnostics[0]["code"], "sdl.mapping_key_conflict")
        self.assertEqual(diagnostics[0]["range"]["start"], {"line": 1, "character": 0})
        related = diagnostics[0]["relatedInformation"][0]
        self.assertEqual(related["location"]["range"]["start"], {"line": 0, "character": 0})

    def test_completion_offers_declared_features(self) -> None:
        uri, _ = self.open(BLOCK_NODE)
        line = BLOCK_NODE.split("\n").index("    features: [app]")
        items = self.complete(uri, line, len("    features: ["))
        self.assertEqual([(item["label"], item["detail"]) for item in items], [("app", "features.app")])

    def test_field_names_are_not_offered_in_value_positions(self) -> None:
        # language_completions returns the nodes field list for /nodes/web/os as well; a field
        # name is never a valid value, so the bridge drops field items after a colon.
        uri, _ = self.open(BLOCK_NODE)
        line = BLOCK_NODE.split("\n").index("    os: linux")
        self.assertEqual(self.complete(uri, line, len("    os: ")), [])

    def test_field_names_are_offered_at_key_positions(self) -> None:
        text = BLOCK_NODE + "    \n"
        uri, _ = self.open(text)
        items = self.complete(uri, text.split("\n").index("    "), len("    "))
        self.assertIn(("type", "type: "), [(item["label"], item["insertText"]) for item in items])
        self.assertTrue(all(item["kind"] == 5 for item in items))

    def test_completion_falls_back_while_yaml_is_incomplete(self) -> None:
        uri, _ = self.open(BLOCK_NODE)
        incomplete = BLOCK_NODE.replace("    features: [app]\n", "    features: [\n")
        diagnostics = self.change(uri, incomplete, 2)
        self.assertEqual(diagnostics[0]["code"], "sdl.parse")
        line = incomplete.split("\n").index("    features: [")
        items = self.complete(uri, line, len("    features: ["))
        self.assertEqual([item["label"] for item in items], ["app"])
        self.assertTrue(items[0]["detail"].endswith(STALE_NOTE))

    def test_completion_forwards_the_issue_1339_mismatch(self) -> None:
        uri, diagnostics = self.open(PARTICIPANTS)
        self.assertEqual(diagnostics, [])
        line = PARTICIPANTS.split("\n").index("    target: agents.two")
        items = self.complete(uri, line, len("    target: "))
        offered = sorted(item["detail"] for item in items)
        # Validation accepts only agents.two here (agents.one is the source); the helper offers all six.
        self.assertEqual(
            offered,
            [
                "agents.one",
                "agents.two",
                "assertions.done",
                "entities.team",
                "propositions.ok",
                "relationships.pair",
            ],
        )

    def test_definition_jumps_to_the_declaration(self) -> None:
        uri, _ = self.open(BLOCK_NODE)
        line = BLOCK_NODE.split("\n").index("    features: [app]")
        locations = self.client.request(
            "textDocument/definition",
            {"textDocument": {"uri": uri}, "position": {"line": line, "character": len("    features: [a")}},
        )
        self.assertEqual(
            locations, [{"uri": uri, "range": {"start": {"line": 2, "character": 2}, "end": {"line": 2, "character": 5}}}]
        )

    def test_malformed_notification_is_logged_and_serving_continues(self) -> None:
        self.client.notify("textDocument/didOpen", {"textDocument": {"uri": "file:///workspace/no-text.sdl.yaml"}})
        message = self.client.wait_for(
            lambda m: m["method"] == "window/logMessage" and "textDocument/didOpen failed" in m["params"]["message"]
        )
        self.assertEqual(message["params"]["type"], 1)
        _, diagnostics = self.open(BLOCK_NODE)
        self.assertEqual(diagnostics, [])

    def test_imports_are_rejected_without_file_context(self) -> None:
        _, diagnostics = self.open("name: composed\nimports:\n  - path: module.yaml\n    namespace: shared\n")
        self.assertEqual(len(diagnostics), 1)
        self.assertIn("SDL imports require file-backed parsing", diagnostics[0]["message"])


@unittest.skipUnless(_raes_available(), f"raes is not importable from {PYTHON}")
class HelperExceptionTest(_Session, unittest.TestCase):
    """The real bridge, with helpers that raise on a marker line (see raising_helpers.py)."""

    script = RAISING_LAUNCHER

    def test_helper_exception_becomes_one_diagnostic(self) -> None:
        _, diagnostics = self.open(f"{BLOCK_NODE}{RAISE_MARKER}\n")
        self.assertEqual([item["code"] for item in diagnostics], ["bridge.helper_exception"])
        self.assertIn("RuntimeError: simulated helper failure", diagnostics[0]["message"])
        _, after = self.open(BLOCK_NODE)
        self.assertEqual(after, [])

    def test_completion_falls_back_when_the_helper_raises(self) -> None:
        uri, _ = self.open(BLOCK_NODE)
        failing = f"{BLOCK_NODE}{RAISE_MARKER}\n"
        self.assertEqual(self.change(uri, failing, 2)[0]["code"], "bridge.helper_exception")
        line = failing.split("\n").index("    features: [app]")
        items = self.complete(uri, line, len("    features: ["))
        self.assertEqual([item["label"] for item in items], ["app"])
        self.assertTrue(items[0]["detail"].endswith(STALE_NOTE))


class MissingRaesTest(unittest.TestCase):
    """A stub `raes` that fails to import, the way an interpreter without raes fails."""

    def test_reports_missing_raes_and_stays_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as stub:
            (Path(stub) / "raes").mkdir()
            (Path(stub) / "raes" / "__init__.py").write_text("raise ImportError('simulated missing raes')\n")
            client, init = _start({"PYTHONPATH": stub})
            try:
                self.assertIn("raes unavailable", init["serverInfo"]["version"])
                message = client.wait_for(lambda m: m["method"] == "window/showMessage", timeout=30)
                self.assertEqual(message["params"]["type"], 1)
                self.assertIn("openraeSdl.python", message["params"]["message"])
                uri = "file:///workspace/missing.sdl.yaml"
                client.notify(
                    "textDocument/didOpen",
                    {"textDocument": {"uri": uri, "languageId": "openrae-sdl", "version": 1, "text": "name: x\n"}},
                )
                items = client.request(
                    "textDocument/completion", {"textDocument": {"uri": uri}, "position": {"line": 1, "character": 0}}
                )
                self.assertEqual(items, {"isIncomplete": False, "items": []})
                self.assertIsNone(client.diagnostics_for(uri))
            finally:
                self.assertEqual(client.close(), 0)


if __name__ == "__main__":
    unittest.main()
