# vscode-raes-sdl

Prototype VS Code support for [OpenRAE](https://github.com/OpenRAE/rae) SDL files
(`*.sdl.yaml`). It was built to answer the feasibility questions in
[OpenRAE/rae#1412](https://github.com/OpenRAE/rae/issues/1412).

This is an exploration, not a product. It is not published to the VS Code Marketplace and it is
not an OpenRAE release. It adds no SDL semantics of its own: every diagnostic, completion and
definition comes from the `raes` package installed in a Python interpreter that you choose.

## What it contains

| Part | Files | What it does |
| --- | --- | --- |
| Language and grammar | `package.json`, `language-configuration.json`, `syntaxes/` | Opens `*.sdl.yaml` as the `openrae-sdl` language. The grammar reuses VS Code's YAML grammar and adds two scopes: top-level SDL keys and `${variable}` placeholders. |
| Schema association | `package.json` (`yamlValidation`), `schemas/` | Associates `*.sdl.yaml` with a bundled copy of rae's published `sdl-authoring-input-v1` schema, for Red Hat's YAML extension. |
| Language-server bridge | `extension.js`, `server/` | Starts `server/raes_sdl_lsp.py` and forwards diagnostics, completion and go-to-definition from `raes.language_service`. The server uses only the Python standard library and `raes`. |
| Tests | `test/` | Grammar tokenization, cursor-to-path mapping, and the bridge driven over stdio the way an editor drives it. |
| Evidence | `evidence/` | Probes and recorded results. See [`evidence/README.md`](evidence/README.md). |

## Two modes

VS Code gives each file one language, which forces a choice:

| | Default: `openrae-sdl` language | YAML mode |
| --- | --- | --- |
| Highlighting | YAML, plus SDL section and placeholder scopes | YAML |
| raes diagnostics, completion and go to definition | Yes | Yes |
| Schema completion and hover | No | Yes |
| Schema diagnostics | No | Yes, including false positives |

Red Hat's YAML extension serves only the languages in its own document selector, so it ignores
files that open as `openrae-sdl`. To use YAML mode, keep that extension installed and add this
user or workspace setting:

```json
"files.associations": { "*.sdl.yaml": "yaml" }
```

## Requirements

- VS Code 1.82 or later.
- Python 3.11 to 3.14 with `raes` installed, for example `python3 -m pip install raes`. The
  installed `raes` version decides the SDL semantics you see. The server reports it in its
  `serverInfo`.
- For YAML mode: Red Hat's YAML extension (`redhat.vscode-yaml`).

## Try it

```console
git clone https://github.com/doublewhy/vscode-raes-sdl.git
cd vscode-raes-sdl
npm ci
code --extensionDevelopmentPath="$PWD" path/to/your/scenarios
```

To install it instead, build a package and use **Extensions: Install from VSIX...**:

```console
npx @vscode/vsce package
```

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `openraeSdl.python` | `python3` | Interpreter in which `raes` is importable. |
| `openraeSdl.languageServer.enabled` | `true` | Start the bridge for SDL documents. |

## Limits

Most of these come from the rae helpers; [`evidence/README.md`](evidence/README.md) has the
measurements.

- The helpers take a JSON-pointer-like path, not a cursor position. `server/sdl_cursor.py` derives
  the path from the text lines, so it keeps working while the YAML is incomplete. It does not
  handle flow collections that span lines, block scalars, anchors, aliases, tags or complex keys.
- Completion needs a document that parses. While it does not, the bridge answers from the last
  version that parsed and marks each item "(from the last parsable version)".
- Field completion returns a section's field list at any depth below the section. The bridge
  drops field names after `key:` and inside flow sequences, where no mapping key can go. It cannot
  correct entry-name positions or nested mappings, such as the keys under `resources:`.
- Reference completion is forwarded unfiltered, so it shows the mismatch in
  [OpenRAE/rae#1339](https://github.com/OpenRAE/rae/issues/1339): a participant relationship
  target offers six declarations, and validation accepts one.
- Semantic diagnostics have no source location. The bridge puts them on the first line and adds
  "(raes reported no source location)". An unknown field is ranged on its value, not its key.
- A document with `imports` is reported as invalid, because the helpers have no file path to
  resolve modules against. There is no workspace index, so go to definition stays in one file.
- Every request parses the whole document. On the largest repository example (46 KB) a request
  took roughly 280 to 350 ms on a busy machine. The helpers refuse input over 64 KiB.
- Each helper turns the parser's and validator's own errors into results, and any other exception
  reaches the caller. The bridge reports a helper that raises as one `bridge.helper_exception`
  diagnostic and keeps running.
- Formatting is not offered, because `language_format` drops comments and rewrites shorthand.
- Positions are converted as code points, while LSP counts UTF-16 code units. They differ only on a
  line that contains a character outside the Basic Multilingual Plane before the position.
- The bundled schema is a copy from one rae commit, so it can disagree with the installed `raes`.
  For example, it declares `execution_policy`, which `raes` 6.0.1 rejects. See
  [`schemas/README.md`](schemas/README.md).
- The schema describes the normalized document, not raw source. YAML mode therefore reports
  accepted shorthand, such as `source: webapp` and `features: [app]`, and case variants, such as
  `type: Switch`, as errors. It also cannot see errors that only rae's semantic validation finds.

## Safety

- The bridge passes the open document's text to `raes.language_service` in-process. It does not
  read other files, use the network or launch scenarios.
- In Restricted Mode, for an untrusted workspace, VS Code ignores a workspace value of
  `openraeSdl.python` (`restrictedConfigurations` in `package.json`), so a cloned repository cannot
  choose the program that runs. The server's working directory is the extension directory.
- In YAML mode, Red Hat's YAML extension can download schemas according to its own settings. For
  example, `yaml.schemaStore.enable` defaults to `true`.

## Tests

```console
npm ci
npm run test:grammar
RAES_PYTHON=/path/to/python-with-raes npm run test:python
```

`RAES_PYTHON` defaults to the interpreter that runs the tests. Bridge tests are skipped when `raes`
is not importable from it. The grammar test downloads VS Code's YAML grammars once, checks their
SHA-256 digests and caches them in `.cache/`. Set `VSCODE_YAML_SYNTAXES` to a directory that
already holds them to run it offline.

On 2026-10-09, all 6 grammar tests and all 25 Python tests passed with `raes` 6.0.1 from PyPI and
with an OpenRAE/rae checkout at commit `35122105b0c1bb648754625d8e3920eafa9bc599`. The GitHub
Actions workflow in `.github/workflows/test.yml` repeats this with `raes` 6.0.1 and builds the
package.

The tests do not start VS Code. They send the server the same LSP messages that
`vscode-languageclient` sends. `extension.js`, which only configures that client, has no automated
test.

## License

MIT, see [`LICENSE`](LICENSE). The bundled schema comes from OpenRAE/rae under its MIT license;
see [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).
