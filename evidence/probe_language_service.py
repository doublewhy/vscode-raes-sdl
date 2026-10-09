"""Editor-relevant behaviour of raes.language_service in an OpenRAE/rae checkout.

Run from anywhere with the checkout's own environment:

    uv run --project <rae>/implementations/python --frozen --all-extras \
        python evidence/probe_language_service.py <rae>

Every section prints what the helpers return; nothing is mocked.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from raes import parse_sdl_file
from raes._language_metadata import SECTION_FIELD_COMPLETIONS
from raes.language_service import (
    _MAX_INPUT_BYTES,
    apply_structured_edit,
    language_completions,
    language_diagnostics,
    language_format,
)

RAE = Path(sys.argv[1]).resolve()
os.chdir(RAE)

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
    target: TARGET
    participant: {kind: cooperation}
"""

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


def heading(title: str) -> None:
    print(f"\n## {title}")


def short(result: dict) -> str:
    return json.dumps(result, sort_keys=True)[:400]


def issue_1339_mismatch() -> None:
    heading("1. Participant relationship target: completion versus validation (issue 1339, audit F5)")
    doc = PARTICIPANTS.replace("TARGET", "agents.two")
    print("document diagnostics:", language_diagnostics(doc)["status"])
    completion = language_completions(doc, cursor_path="/relationships/pair/target")
    print("completion context:", completion["context"])
    for item in completion["items"]:
        verdict = language_diagnostics(PARTICIPANTS.replace("TARGET", item["insert_text"]))
        messages = [d["message"] for d in verdict["diagnostics"]]
        print(f"  offered {item['detail']:<20} insert {item['insert_text']!r:<8} -> {verdict['status']} {messages}")


def field_completion_drift() -> None:
    heading("2. Field completion lists versus the published schema")
    schema = json.loads(Path("contracts/schemas/sdl/sdl-authoring-input-v1.json").read_text(encoding="utf-8"))
    defs = schema["$defs"]

    def entry_properties(node: object) -> set[str]:
        stack, found, steps = [node], set(), 0
        while stack and steps < 500:
            steps += 1
            current = stack.pop()
            while isinstance(current, dict) and "$ref" in current:
                current = defs[current["$ref"].rsplit("/", 1)[-1]]
            if not isinstance(current, dict):
                continue
            for key in ("anyOf", "oneOf", "allOf"):
                stack.extend(current.get(key, []))
            if current.get("properties"):
                found |= set(current["properties"])
            elif current.get("type") == "object":
                if isinstance(current.get("additionalProperties"), dict):
                    stack.append(current["additionalProperties"])
                stack.extend(current.get("patternProperties", {}).values())
            elif current.get("type") == "array" and isinstance(current.get("items"), dict):
                stack.append(current["items"])
        return found

    missing_total = 0
    drifting = 0
    for section, offered in sorted(SECTION_FIELD_COMPLETIONS.items()):
        published = entry_properties(schema["properties"][section])
        missing, extra = sorted(published - set(offered)), sorted(set(offered) - published)
        if missing or extra:
            drifting += 1
            missing_total += len(missing)
            print(f"  {section}: offers {len(offered)}, schema declares {len(published)}; not offered {missing}; not in schema {extra}")
    metadata = {"name", "version", "description", "semantic_revision", "module", "imports"}
    unlisted = sorted(set(schema["properties"]) - set(SECTION_FIELD_COMPLETIONS) - metadata)
    print(f"sections with drift: {drifting}/{len(SECTION_FIELD_COMPLETIONS)}; schema fields never offered: {missing_total}")
    print(f"sections without a field list ({len(unlisted)}): {unlisted}")
    offered = language_completions("name: demo\nfeatures:\n  app: {type: service}\n", cursor_path="/features/app", prefix="v")
    print("features field completion with prefix 'v':", [item["label"] for item in offered["items"]])
    verdict = language_diagnostics("name: demo\nfeatures:\n  app: {type: service, version: '1.0'}\n")
    print("feature with that field:", [(d["code"], d["message"], d.get("path")) for d in verdict["diagnostics"]])


def incomplete_documents() -> None:
    heading("3. Completion on documents being typed")
    cases = {
        "complete document": BLOCK_NODE,
        "key typed with no value": BLOCK_NODE.replace("    features: [app]\n", "    features:\n"),
        "unclosed flow sequence": BLOCK_NODE.replace("    features: [app]\n", "    features: [\n"),
        "key typed without its colon": BLOCK_NODE.replace("    features: [app]\n", "    fea\n"),
        "unrelated legacy spelling elsewhere": BLOCK_NODE.replace("type: compute", "type: VM"),
    }
    for label, text in cases.items():
        result = language_completions(text, cursor_path="/nodes/web/features")
        detail = [item["label"] for item in result["items"]] if result["status"] == "ok" else result["diagnostics"][0]["code"]
        print(f"  {label:<38} -> {result['status']}: {detail}")


def diagnostic_ranges() -> None:
    heading("4. Diagnostic source locations")
    unknown = BLOCK_NODE.replace("    features: [app]\n", "    features: [app]\n    colour: blue\n")
    for label, text in {
        "unknown field": unknown,
        "unresolved reference": BLOCK_NODE.replace("[app]", "[missing]"),
        "duplicate key": "name: demo\nname: again\n",
        "YAML syntax error": "name: demo\nnodes:\n  web: {type: compute\n",
    }.items():
        for item in language_diagnostics(text)["diagnostics"]:
            print(f"  {label:<22} stage={item['stage']:<20} code={item['code']:<26} path={item.get('path')!r} range={item.get('range')}")
    line = unknown.split("\n")[9]
    print(f"  (unknown field line: key at column {line.index('colour') + 1}, value at column {line.index('blue') + 1}, 1-based)")


def formatting() -> None:
    heading("5. Formatting")
    source = "# scenario header\nname: demo  # trailing\nfeatures:\n  # feature comment\n  app: {type: Service, source: webapp}\n"
    result = language_format(source)
    print("status:", result["status"], "| comments kept:", "#" in result["content"])
    print(result["content"].rstrip())


def imports() -> None:
    heading("6. Module imports")
    root = Path("contracts/fixtures/sdl/variation-points-v1/composition/root.yaml")
    print(f"parse_sdl_file({root}):", type(parse_sdl_file(root)).__name__)
    text = root.read_text(encoding="utf-8")
    print("language_diagnostics:", short(language_diagnostics(text)))
    print("language_diagnostics(semantic_validation=False):", short(language_diagnostics(text, semantic_validation=False)))


def completion_depth() -> None:
    heading("8. Field completion below the section level")
    for path in ("/nodes", "/nodes/web", "/nodes/web/resources", "/nodes/web/os"):
        result = language_completions(BLOCK_NODE, cursor_path=path)
        print(f"  {path:<22} context={result['context']:<15} {[item['label'] for item in result['items']]}")


def structured_edit() -> None:
    heading("9. Structured edits")
    source = "# scenario header\n" + BLOCK_NODE.replace("os: linux", "os: linux  # trailing")
    result = apply_structured_edit(source, operation="set", pointer="/nodes/web/os", value="windows")
    print("status:", result["status"], "| comments kept:", "#" in result["content"])
    print(result["content"].rstrip())


def input_limit() -> None:
    heading("7. Input size limit")
    files = sorted(p for p in Path(".").rglob("*.sdl.yaml") if ".git" not in p.parts and ".venv" not in p.parts)
    largest = max(files, key=lambda p: p.stat().st_size)
    over = [p for p in files if p.stat().st_size > _MAX_INPUT_BYTES]
    print(f"limit {_MAX_INPUT_BYTES} bytes; {len(files)} *.sdl.yaml files; {len(over)} over the limit; largest {largest} ({largest.stat().st_size} bytes)")


if __name__ == "__main__":
    commit = subprocess.run(["git", "-C", str(RAE), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    print(f"rae checkout at commit {commit.stdout.strip()}")
    for probe in (
        issue_1339_mismatch,
        field_completion_drift,
        incomplete_documents,
        diagnostic_ranges,
        formatting,
        imports,
        input_limit,
        completion_depth,
        structured_edit,
    ):
        probe()
