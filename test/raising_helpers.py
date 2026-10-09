"""Start the bridge with raes helpers that raise whenever the text contains a marker line.

The bridge must keep serving when a helper raises instead of returning a result. When run as a
script, this file wraps ``language_diagnostics`` and ``language_completions`` so that any text
containing ``MARKER`` raises, then runs ``server/raes_sdl_lsp.py`` unchanged. Text without the
marker reaches the real helpers.
"""

from __future__ import annotations

import runpy
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

MARKER = "# test: the helper raises"
SERVER = Path(__file__).resolve().parents[1] / "server" / "raes_sdl_lsp.py"


def raising_on_marker(helper: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(helper)
    def wrapper(sdl_content: str, *args: Any, **kwargs: Any) -> Any:
        if MARKER in sdl_content:
            raise RuntimeError("simulated helper failure")
        return helper(sdl_content, *args, **kwargs)

    return wrapper


def main() -> None:
    from raes import language_service

    for name in ("language_diagnostics", "language_completions"):
        setattr(language_service, name, raising_on_marker(getattr(language_service, name)))
    runpy.run_path(str(SERVER), run_name="__main__")


if __name__ == "__main__":
    main()
