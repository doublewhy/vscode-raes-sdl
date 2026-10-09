"""Validate raw SDL source against the published authoring schema, as a YAML schema association does.

    uv run --project <rae>/implementations/python --frozen --all-extras \
        python evidence/probe_schema.py <rae>

Only documents that rae's own language_diagnostics accepts are counted as examples, so every
schema error reported for them is a false positive of the raw-source association.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import yaml
from raes.language_service import language_diagnostics

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import ACCEPTED, REJECTED  # noqa: E402

RAE = Path(sys.argv[1]).resolve()
schema = json.loads((RAE / "contracts/schemas/sdl/sdl-authoring-input-v1.json").read_text(encoding="utf-8"))
validator = jsonschema.Draft202012Validator(schema)


def schema_errors(text: str) -> list[str]:
    errors = []
    for error in validator.iter_errors(yaml.safe_load(text)):
        best = jsonschema.exceptions.best_match([error])
        errors.append(f"/{'/'.join(map(str, best.absolute_path))}: {best.message[:110]}")
    return errors


examples = sorted([*(RAE / "examples").rglob("*.sdl.yaml"), *(RAE / "docs/public/_static/examples").rglob("*.sdl.yaml")])
accepted = [p for p in examples if language_diagnostics(p.read_text(encoding="utf-8"))["status"] == "valid"]
flagged = {p: schema_errors(p.read_text(encoding="utf-8")) for p in accepted}
print(f"example files: {len(examples)}; accepted by rae: {len(accepted)}; with raw-schema errors: {sum(bool(v) for v in flagged.values())}")
for path, errors in flagged.items():
    if errors:
        print(f"  {path.relative_to(RAE)}: {errors}")

print("\naccepted by rae (schema errors here are false positives):")
for label, text in ACCEPTED.items():
    assert language_diagnostics(text)["status"] == "valid", label
    print(f"  {label:<32} schema: {schema_errors(text) or 'no errors'}")

print("\nrejected by rae (schema silence here is a false negative):")
for label, text in REJECTED.items():
    codes = [d["code"] for d in language_diagnostics(text)["diagnostics"]]
    print(f"  {label:<32} rae: {codes}; schema: {schema_errors(text) or 'no errors'}")
