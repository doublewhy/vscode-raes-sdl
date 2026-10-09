"""Run yaml-language-server headlessly with this extension's yamlValidation association.

The Red Hat YAML extension turns every installed extension's `contributes.yamlValidation` entry
into a `json/schemaAssociations` notification (see `getSchemaAssociations` in its
src/extension.ts). This script sends the notification that package.json's entry produces,
`{"fileMatch": ["/*.sdl.yaml"], "uri": <bundled schema>}`, opens documents, and records the
diagnostics, completion and hover an author would see. VS Code itself is not involved.

    npm install --prefix /tmp/yls yaml-language-server@1.24.0
    uv run --project <rae>/implementations/python --frozen --all-extras \
        python evidence/probe_yaml_language_server.py <rae> /tmp/yls
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "test"))
from cases import ACCEPTED, REJECTED  # noqa: E402
from lsp_client import LspClient  # noqa: E402

RAE = Path(sys.argv[1]).resolve()
YLS = Path(sys.argv[2]).resolve() / "node_modules" / "yaml-language-server" / "bin" / "yaml-language-server"
SCHEMA_URI = (HERE.parent / "schemas" / "sdl-authoring-input-v1.json").as_uri()
SETTINGS = {"yaml": {"validate": True, "hover": True, "completion": True, "format": {"enable": False}, "schemaStore": {"enable": False}}}

client = LspClient(["node", str(YLS), "--stdio"], SETTINGS)
workspace = Path(tempfile.mkdtemp(prefix="yls-probe-"))
capabilities = {
    "textDocument": {"publishDiagnostics": {}, "completion": {"completionItem": {}}, "hover": {"contentFormat": ["markdown"]}},
    "workspace": {"configuration": True, "didChangeConfiguration": {"dynamicRegistration": True}},
}
init = client.request("initialize", {"processId": None, "rootUri": workspace.as_uri(), "capabilities": capabilities})
print("server:", init.get("serverInfo"))
client.notify("initialized", {})
client.notify("workspace/didChangeConfiguration", {"settings": SETTINGS})
# vscode-languageclient sends an array argument as one positional parameter, so the wire
# params are a one-element array that holds the association list.
client.notify("json/schemaAssociations", [[{"fileMatch": ["/*.sdl.yaml"], "uri": SCHEMA_URI}]])
client.settle(1.0)

examples = sorted([*(RAE / "examples").rglob("*.sdl.yaml"), *(RAE / "docs/public/_static/examples").rglob("*.sdl.yaml")])
documents = {str(p.relative_to(RAE)): p.read_text(encoding="utf-8") for p in examples}
documents |= {f"accepted case: {k}": v for k, v in ACCEPTED.items()}
documents |= {f"rejected case: {k}": v for k, v in REJECTED.items()}
uris = {}
for index, (label, text) in enumerate(documents.items()):
    uris[label] = (workspace / f"doc{index:02d}.sdl.yaml").as_uri()
    client.notify("textDocument/didOpen", {"textDocument": {"uri": uris[label], "languageId": "yaml", "version": 1, "text": text}})
deadline = time.monotonic() + 600
while time.monotonic() < deadline and any(client.diagnostics_for(uri) is None for uri in uris.values()):
    client.pump(0.5)

clean_examples = 0
for label, uri in uris.items():
    diagnostics = client.diagnostics_for(uri)
    if diagnostics is None:
        print(f"[{label}] no diagnostics notification")
        continue
    if not label.startswith(("accepted case", "rejected case")) and not diagnostics:
        clean_examples += 1
        continue
    rendered = [f"{d['range']['start']['line'] + 1}:{d['range']['start']['character'] + 1} {d['message'][:90]}" for d in diagnostics]
    print(f"[{label}] {rendered or 'no diagnostics'}")
print(f"examples without diagnostics: {clean_examples}/{len(examples)}")

probe = "name: demo\nnodes:\n  web:\n    type: compute\n    \n"
uri = (workspace / "assist.sdl.yaml").as_uri()
client.notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": "yaml", "version": 1, "text": probe}})
client.settle(1.0)
completion = client.request("textDocument/completion", {"textDocument": {"uri": uri}, "position": {"line": 4, "character": 4}})
items = completion.get("items", []) if isinstance(completion, dict) else completion or []
print(f"field completion inside /nodes/web: {len(items)} items: {sorted(item['label'] for item in items)}")
hover = client.request("textDocument/hover", {"textDocument": {"uri": uri}, "position": {"line": 3, "character": 5}})
print("hover on /nodes/web/type:", json.dumps((hover or {}).get("contents")).replace(SCHEMA_URI, "<bundled schema>")[:240])
client.close()
