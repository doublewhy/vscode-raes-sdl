"""Cursor-to-path mapping used by the bridge before it calls raes.language_service."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from sdl_cursor import cursor_context, cursor_path, encode_pointer, word_at  # noqa: E402

CURSOR = "|"


def _locate(marked: str) -> tuple[str, int, int]:
    """Strip the single cursor marker and return text, zero-based line and character."""
    before, _, after = marked.partition(CURSOR)
    line = before.count("\n")
    character = len(before) - (before.rfind("\n") + 1)
    return before + after, line, character


CASES = [
    ("empty document", "|", ""),
    ("top-level key position", "name: demo\n|", ""),
    ("entry-name position under a section", "name: demo\nnodes:\n  |", "/nodes"),
    ("field position inside an entry", "nodes:\n  web:\n    type: compute\n    |", "/nodes/web"),
    ("key typed without its colon", "nodes:\n  web:\n    fea|", "/nodes/web"),
    ("block value after a colon", "nodes:\n  web:\n    features: |", "/nodes/web/features"),
    ("value directly after the colon", "nodes:\n  web:\n    features:|", "/nodes/web/features"),
    ("unclosed flow sequence", "nodes:\n  web:\n    features: [app, |", "/nodes/web/features"),
    ("closed flow sequence before cursor", "nodes:\n  web:\n    features: [app] |", "/nodes/web/features"),
    (
        "flow mapping on the entry line",
        "nodes:\n  web: {type: compute, features: [|",
        "/nodes/web/features",
    ),
    ("nested flow mappings", "a:\n  b: {c: {d: |", "/a/b/c/d"),
    ("indented block sequence item", "infrastructure:\n  web:\n    links:\n      - |", "/infrastructure/web/links"),
    ("compact block sequence item", "infrastructure:\n  web:\n    links:\n    - net1\n    - |", "/infrastructure/web/links"),
    (
        "sibling entries with inline values are not ancestors",
        "nodes:\n  db: {type: compute}\n  web:\n    features: |",
        "/nodes/web/features",
    ),
    ("comments and blank lines are skipped", "nodes:\n  # note\n\n  web:\n    |", "/nodes/web"),
    ("quoted keys are unquoted", 'nodes:\n  "web":\n    |', "/nodes/web"),
    (
        "key inside a sequence item",
        "forwarding_agents:\n  - name: relay\n    targets:\n      - |",
        "/forwarding_agents/targets",
    ),
    ("document start marker stops the search", "nodes:\n---\n  |", ""),
]


class CursorPathTest(unittest.TestCase):
    def test_cases(self) -> None:
        for label, marked, expected in CASES:
            with self.subTest(label):
                text, line, character = _locate(marked)
                self.assertEqual(cursor_path(text, line, character), expected)

    def test_comment_position_has_no_path(self) -> None:
        text, line, character = _locate("nodes:\n  web:  # features: |")
        self.assertIsNone(cursor_path(text, line, character))

    def test_hash_inside_quotes_is_not_a_comment(self) -> None:
        text, line, character = _locate('nodes:\n  web:\n    description: "a # b" |')
        self.assertEqual(cursor_path(text, line, character), "/nodes/web/description")

    def test_position_past_end_maps_to_document(self) -> None:
        self.assertEqual(cursor_path("name: demo", 5, 0), "")

    def test_pointer_escaping(self) -> None:
        self.assertEqual(encode_pointer(["a/b", "c~d"]), "/a~1b/c~0d")


# (label, marked text, expected path, expected value_position)
POSITION_KINDS = [
    ("block value after a colon", "nodes:\n  web:\n    os: |", "/nodes/web/os", True),
    ("field position inside an entry", "nodes:\n  web:\n    |", "/nodes/web", False),
    ("key typed without its colon", "nodes:\n  web:\n    o|", "/nodes/web", False),
    ("flow sequence item", "nodes:\n  web:\n    features: [app, |", "/nodes/web/features", True),
    ("flow mapping key", "nodes:\n  web: {type: compute, |", "/nodes/web", False),
    ("flow mapping value", "nodes:\n  web: {type: |", "/nodes/web/type", True),
    ("block sequence item may start a mapping", "forwarding_agents:\n  - |", "/forwarding_agents", False),
    ("flow sequence inside a block sequence item", "a:\n  - [x, |", "/a", True),
    ("key inside a block sequence item", "forwarding_agents:\n  - name: |", "/forwarding_agents/name", True),
]


class PositionKindTest(unittest.TestCase):
    def test_value_positions(self) -> None:
        for label, marked, path, value_position in POSITION_KINDS:
            with self.subTest(label):
                text, line, character = _locate(marked)
                context = cursor_context(text, line, character)
                self.assertIsNotNone(context)
                self.assertEqual((context.path, context.value_position), (path, value_position))

    def test_comment_position_has_no_context(self) -> None:
        text, line, character = _locate("nodes:\n  web:  # os: |")
        self.assertIsNone(cursor_context(text, line, character))


class WordAtTest(unittest.TestCase):
    def test_qualified_reference_is_one_word(self) -> None:
        self.assertEqual(word_at("    target: agents.two\n", 0, 18), "agents.two")

    def test_word_boundaries(self) -> None:
        text = "    features: [app, db]\n"
        self.assertEqual(word_at(text, 0, text.index("app")), "app")
        self.assertEqual(word_at(text, 0, text.index("db") + 2), "db")
        self.assertIsNone(word_at(text, 0, text.index("[")))
        self.assertIsNone(word_at(text, 3, 0))


if __name__ == "__main__":
    unittest.main()
