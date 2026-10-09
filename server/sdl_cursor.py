"""Map an editor cursor to the path argument that ``raes.language_service`` expects.

The rae helpers take a JSON-pointer-like ``cursor_path`` such as ``/nodes/web/features``
instead of a line and column, so every editor client has to supply this mapping. This
module works on raw text lines, so it still answers while the YAML is syntactically
incomplete (an unclosed ``[``, a key typed without its colon).

Supported: block mappings, block sequences (indented or compact), and flow collections
that open and close on the cursor's line. Not supported: flow collections spanning lines,
block scalar content, anchors, aliases, tags, and complex keys. Sequence indices are not
emitted because the helpers ignore them.

The mapper also reports whether the cursor sits in a value position (after ``key:`` or
inside a flow sequence), where a mapping key cannot be inserted. A block sequence item
(``- ``) is not reported as a value position because it may start a mapping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_KEY = r"(?:[A-Za-z0-9_][A-Za-z0-9_.\-]*|\"[^\"\n]*\"|'[^'\n]*')"
_KEY_LINE = re.compile(rf"^(?P<indent> *)(?P<dashes>(?:- +)*)(?P<key>{_KEY}) *:(?: +|$)(?P<rest>.*)$")
_DASH_LINE = re.compile(r"^(?P<indent> *)(?P<dashes>(?:- *)+)(?P<rest>.*)$")
_WORD = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\-]*")
_FLOW_KEY = re.compile(rf"\s*(?P<key>{_KEY})\s*:(?:\s|$)")


@dataclass(frozen=True)
class CursorContext:
    """The helper ``cursor_path`` for a position and whether it is a value position."""

    path: str
    value_position: bool


@dataclass(frozen=True)
class _LineContext:
    """Where the cursor sits on its own line."""

    tokens: tuple[str, ...]
    limit: int
    compact_parent: bool
    value_position: bool


def encode_pointer(tokens: list[str] | tuple[str, ...]) -> str:
    """Encode path tokens as an RFC 6901 JSON pointer."""
    if not tokens:
        return ""
    return "/" + "/".join(token.replace("~", "~0").replace("/", "~1") for token in tokens)


def cursor_context(text: str, line: int, character: int) -> CursorContext | None:
    """Return the path and position kind for a zero-based position, or None inside a comment."""
    lines = text.split("\n")
    if line < 0 or line >= len(lines):
        return CursorContext(encode_pointer([]), value_position=False)
    before = lines[line][: max(character, 0)]
    if _in_comment(before):
        return None
    context = _line_context(before)
    ancestors = _ancestors(lines, line, context.limit, compact_parent=context.compact_parent)
    return CursorContext(encode_pointer([*ancestors, *context.tokens]), context.value_position)


def cursor_path(text: str, line: int, character: int) -> str | None:
    """Return the helper ``cursor_path`` for a zero-based position, or None inside a comment."""
    context = cursor_context(text, line, character)
    return None if context is None else context.path


def word_at(text: str, line: int, character: int) -> str | None:
    """Return the SDL identifier (qualified names included) under a zero-based position."""
    lines = text.split("\n")
    if line < 0 or line >= len(lines):
        return None
    for match in _WORD.finditer(lines[line]):
        if match.start() <= character <= match.end():
            return match.group(0)
    return None


def _in_comment(before: str) -> bool:
    quote: str | None = None
    for index, char in enumerate(before):
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#" and (index == 0 or before[index - 1].isspace()):
            return True
    return False


def _line_context(before: str) -> _LineContext:
    key_line = _KEY_LINE.match(before)
    if key_line:
        # Cursor is in the value of `key` (possibly inside a flow collection).
        dash_column = len(key_line["indent"])
        flow_tokens, expects = _flow_state(key_line["rest"])
        return _LineContext(
            (_unquote(key_line["key"]), *flow_tokens),
            dash_column,
            compact_parent=bool(key_line["dashes"]),
            value_position=expects != "key",
        )
    dash_line = _DASH_LINE.match(before)
    if dash_line:
        # Cursor is in a sequence item; the owning key is above.
        flow_tokens, expects = _flow_state(dash_line["rest"])
        return _LineContext(
            flow_tokens, len(dash_line["indent"]), compact_parent=True, value_position=expects == "value"
        )
    # Cursor is at a key position (blank line or a key typed without its colon).
    return _LineContext((), len(before) - len(before.lstrip(" ")), compact_parent=False, value_position=False)


def _ancestors(lines: list[str], line: int, limit: int, *, compact_parent: bool) -> list[str]:
    tokens: list[str] = []
    for index in range(line - 1, -1, -1):
        if limit == 0 and not compact_parent:
            break
        raw = lines[index]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped in {"---", "..."}:
            break
        limit, compact_parent = _visit_ancestor_line(raw, tokens, limit, compact_parent)
    return tokens


def _visit_ancestor_line(raw: str, tokens: list[str], limit: int, compact_parent: bool) -> tuple[int, bool]:
    key_line = _KEY_LINE.match(raw)
    dash_line = _DASH_LINE.match(raw)
    if key_line:
        dash_column = len(key_line["indent"])
        key_column = dash_column + len(key_line["dashes"])
        opens_block = not key_line["rest"].strip() or key_line["rest"].lstrip().startswith("#")
        compact_owner = compact_parent and key_column == limit and not key_line["dashes"]
        if opens_block and (key_column < limit or compact_owner):
            tokens.insert(0, _unquote(key_line["key"]))
            if key_line["dashes"]:
                return dash_column, True
            return key_column, False
        if key_line["dashes"] and dash_column < limit:
            return dash_column, True
        return limit, compact_parent
    if dash_line and len(dash_line["indent"]) < limit:
        return len(dash_line["indent"]), True
    return limit, compact_parent


def _flow_state(rest: str) -> tuple[tuple[str, ...], str | None]:
    """Keys leading to the cursor inside flow collections opened earlier on the line.

    Also returns what the innermost open collection expects at the cursor: None when no
    collection is open, "value" for a flow sequence item or a flow mapping value, and "key"
    for a flow mapping key.
    """
    stack: list[dict[str, str | None]] = []
    quote: str | None = None
    segment_start = 0
    for index, char in enumerate(rest):
        if quote:
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char in "[{":
            _record_flow_key(stack, rest[segment_start:index])
            stack.append({"kind": char, "key": None})
            segment_start = index + 1
        elif char in "]}" and stack:
            stack.pop()
            segment_start = index + 1
        elif char == "," and stack:
            stack[-1]["key"] = None
            segment_start = index + 1
    if stack:
        _record_flow_key(stack, rest[segment_start:])
    tokens = tuple(str(entry["key"]) for entry in stack if entry["kind"] == "{" and entry["key"] is not None)
    if not stack:
        return tokens, None
    innermost = stack[-1]
    return tokens, "value" if innermost["kind"] == "[" or innermost["key"] is not None else "key"


def _record_flow_key(stack: list[dict[str, str | None]], segment: str) -> None:
    if not stack or stack[-1]["kind"] != "{":
        return
    match = _FLOW_KEY.match(segment)
    if match:
        stack[-1]["key"] = _unquote(match["key"])


def _unquote(key: str) -> str:
    if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
        return key[1:-1]
    return key
