"""Rough cost of calling the rae helpers from an editor process.

    uv run --project <rae>/implementations/python --frozen --all-extras \
        python evidence/probe_latency.py <rae>

Prints the median warm in-process time on the largest repository example and the cold cost of a
fresh interpreter that imports raes and makes one call. Treat the numbers as indicative only:
they depend on the machine and its load.
"""

from __future__ import annotations

import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

from raes.language_service import language_completions, language_diagnostics

RAE = Path(sys.argv[1]).resolve()
target = max((RAE / "examples").rglob("*.sdl.yaml"), key=lambda p: p.stat().st_size)
text = target.read_text(encoding="utf-8")
print(f"python {sys.version.split()[0]}; load average {os.getloadavg()[0]:.1f}; file {target.relative_to(RAE)} ({len(text.encode())} bytes)")
for label, call in (
    ("diagnostics", lambda: language_diagnostics(text)),
    ("completions", lambda: language_completions(text, cursor_path="/nodes")),
):
    samples = []
    for _ in range(5):
        start = time.perf_counter()
        call()
        samples.append(time.perf_counter() - start)
    print(f"warm {label}: median {statistics.median(samples) * 1000:.0f} ms over 5 calls")
cold = []
snippet = f"import pathlib; from raes.language_service import language_diagnostics; language_diagnostics(pathlib.Path({str(target)!r}).read_text())"
for _ in range(3):
    start = time.perf_counter()
    subprocess.run([sys.executable, "-c", snippet], check=True)
    cold.append(time.perf_counter() - start)
print(f"cold interpreter (import raes + one diagnostics call): median {statistics.median(cold) * 1000:.0f} ms over 3 runs")
