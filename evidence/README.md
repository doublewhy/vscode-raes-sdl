# Evidence

These scripts record what the OpenRAE helpers and a schema-only YAML integration report for the
same SDL documents. Nothing is mocked: each script imports `raes` from the interpreter that runs
it, and `probe_yaml_language_server.py` drives the real `yaml-language-server` over stdio.

The results below were recorded on 2026-10-09 against an
[OpenRAE/rae](https://github.com/OpenRAE/rae) checkout at commit
`35122105b0c1bb648754625d8e3920eafa9bc599` (the `dev` branch on that date), with
`yaml-language-server` 1.24.0 from npm. That is the version Red Hat's VS Code YAML extension 1.24.0
depends on, its latest release on that date.

| Script | Question it answers |
| --- | --- |
| `probe_language_service.py` | What do `raes.language_service` completion, diagnostics, formatting and edits return for editor-shaped inputs? |
| `probe_schema.py` | What does validating raw SDL source against the published authoring schema report, compared with rae? |
| `probe_yaml_language_server.py` | What would an author see from the schema association alone (diagnostics, completion, hover)? |
| `probe_latency.py` | Roughly how long do the helpers take on the largest repository example? |

`cases.py` holds the small documents shared by the schema and YAML-server probes. Two probes read
private helper state (`raes._language_metadata.SECTION_FIELD_COMPLETIONS` and
`raes.language_service._MAX_INPUT_BYTES`) to compare it with the published schema; the bridge in
`server/` uses only the public `raes.language_service` functions.

## Run

From this repository, with `<rae>` an OpenRAE/rae checkout:

```console
uv run --project <rae>/implementations/python --frozen --all-extras python evidence/probe_language_service.py <rae>
uv run --project <rae>/implementations/python --frozen --all-extras python evidence/probe_schema.py <rae>
npm install --prefix /tmp/yls yaml-language-server@1.24.0
uv run --project <rae>/implementations/python --frozen --all-extras python evidence/probe_yaml_language_server.py <rae> /tmp/yls
uv run --project <rae>/implementations/python --frozen --all-extras python evidence/probe_latency.py <rae>
```

## Language-service behavior

```text
rae checkout at commit 35122105b0c1bb648754625d8e3920eafa9bc599

## 1. Participant relationship target: completion versus validation (issue 1339, audit F5)
document diagnostics: valid
completion context: reference:targetable
  offered agents.one           insert 'one'    -> invalid ["Relationship 'pair' requires distinct participants"]
  offered agents.two           insert 'two'    -> valid []
  offered assertions.done      insert 'done'   -> invalid ["Relationship 'pair' target participant endpoint must resolve unambiguously to a declared agent"]
  offered entities.team        insert 'team'   -> invalid ["Relationship 'pair' target participant endpoint must resolve unambiguously to a declared agent"]
  offered propositions.ok      insert 'ok'     -> invalid ["Relationship 'pair' target participant endpoint must resolve unambiguously to a declared agent"]
  offered relationships.pair   insert 'pair'   -> invalid ["Relationship 'pair' target participant endpoint must resolve unambiguously to a declared agent"]

## 2. Field completion lists versus the published schema
  accounts: offers 7, schema declares 14; not offered ['description', 'disabled', 'groups', 'home', 'mail', 'materialization_profile', 'shell']; not in schema []
  agents: offers 7, schema declares 12; not offered ['allowed_subnets', 'authority_anchors', 'description', 'observation_boundaries', 'operating_scope']; not in schema []
  behavior_specifications: offers 17, schema declares 18; not offered ['autonomous_execution']; not in schema []
  conditions: offers 5, schema declares 10; not offered ['environment', 'name', 'retries', 'start_period', 'timeout']; not in schema []
  content: offers 7, schema declares 13; not offered ['description', 'destination', 'sensitive', 'tags', 'text', 'text_from']; not in schema []
  entities: offers 4, schema declares 7; not offered ['description', 'events', 'mission']; not in schema []
  events: offers 2, schema declares 5; not offered ['description', 'name', 'source']; not in schema []
  evidence_requirements: offers 17, schema declares 24; not offered ['capture_requirement_ref', 'capture_spec_ref', 'description', 'field_selectors', 'notes', 'observation_demand', 'output_contract']; not in schema []
  features: offers 4, schema declares 7; not offered ['description', 'destination', 'environment', 'name']; not in schema ['version']
  infrastructure: offers 4, schema declares 6; not offered ['acls', 'description']; not in schema []
  injects: offers 3, schema declares 6; not offered ['description', 'environment', 'name']; not in schema []
  nodes: offers 9, schema declares 16; not offered ['architecture', 'asset_value', 'injects', 'os_distribution', 'os_version', 'runtime', 'source']; not in schema []
  objectives: offers 7, schema declares 9; not offered ['description', 'name']; not in schema []
  realization: offers 2, schema declares 3; not offered ['constraints']; not in schema []
  relationships: offers 11, schema declares 17; not offered ['database_access', 'description', 'forwarding_edge', 'mail_access', 'proxy_upstream', 'service_integration']; not in schema []
  scripts: offers 4, schema declares 6; not offered ['description', 'name']; not in schema []
  stories: offers 2, schema declares 4; not offered ['description', 'name']; not in schema []
  workflows: offers 2, schema declares 5; not offered ['compensation', 'description', 'timeout']; not in schema []
sections with drift: 18/33; schema fields never offered: 69
sections without a field list (7): ['action_contracts', 'execution_policy', 'forwarding_agents', 'generated_artifacts', 'observation_boundaries', 'outcome_interpretation_rules', 'persistent_volumes']
features field completion with prefix 'v': ['version']
feature with that field: [('sdl.model.invalid', 'Extra inputs are not permitted', '/features/app/version')]

## 3. Completion on documents being typed
  complete document                      -> ok: ['app']
  key typed with no value                -> ok: ['app']
  unclosed flow sequence                 -> invalid: sdl.parse
  key typed without its colon            -> invalid: sdl.parse
  unrelated legacy spelling elsewhere    -> invalid: sdl.legacy_node_type_vm

## 4. Diagnostic source locations
  unknown field          stage=parse                code=sdl.model.invalid          path='/nodes/web/colour' range={'start': {'line': 10, 'column': 13}, 'end': {'line': 10, 'column': 17}}
  unresolved reference   stage=semantic_validation  code=sdl.semantic               path=None range=None
  duplicate key          stage=parse                code=sdl.mapping_key_conflict   path='/name' range={'start': {'line': 2, 'column': 1}, 'end': {'line': 2, 'column': 5}}
  YAML syntax error      stage=parse                code=sdl.parse                  path='' range={'start': {'line': 4, 'column': 1}, 'end': {'line': 4, 'column': 1}}
  (unknown field line: key at column 5, value at column 13, 1-based)

## 5. Formatting
status: formatted | comments kept: False
name: demo
features:
  app:
    type: service
    source:
      name: webapp
      version: '*'

## 6. Module imports
parse_sdl_file(contracts/fixtures/sdl/variation-points-v1/composition/root.yaml): ExpandedScenario
language_diagnostics: {"diagnostics": [{"code": "sdl.parse", "message": "SDL imports require file-backed parsing via parse_sdl_file()", "severity": "error", "stage": "parse"}], "stage": "parse", "status": "invalid"}
language_diagnostics(semantic_validation=False): {"diagnostics": [{"code": "sdl.parse", "message": "SDL imports require file-backed parsing via parse_sdl_file()", "severity": "error", "stage": "parse"}], "stage": "parse", "status": "invalid"}

## 7. Input size limit
limit 65536 bytes; 40 *.sdl.yaml files; 0 over the limit; largest examples/scenarios/hospital-ransomware-surgery-day.sdl.yaml (46073 bytes)

## 8. Field completion below the section level
  /nodes                 context=section:nodes   ['type', 'description', 'os', 'resources', 'features', 'conditions', 'services', 'roles', 'endpoint_persona']
  /nodes/web             context=section:nodes   ['type', 'description', 'os', 'resources', 'features', 'conditions', 'services', 'roles', 'endpoint_persona']
  /nodes/web/resources   context=section:nodes   ['type', 'description', 'os', 'resources', 'features', 'conditions', 'services', 'roles', 'endpoint_persona']
  /nodes/web/os          context=section:nodes   ['type', 'description', 'os', 'resources', 'features', 'conditions', 'services', 'roles', 'endpoint_persona']

## 9. Structured edits
status: edited | comments kept: False
name: demo
features:
  app:
    type: service
    source:
      name: webapp
      version: '*'
nodes:
  web:
    type: compute
    os: windows
    resources:
      ram: 2 GiB
      cpu: 1
    features:
      app: ''
```

Reading the output:

- Section 1: completion for a participant relationship target offers six declarations, and
  validation accepts one. This is the editor mismatch tracked in
  [OpenRAE/rae#1339](https://github.com/OpenRAE/rae/issues/1339).
- Section 2: hand-maintained field lists lag the published schema in 18 of 33 sections (69 schema
  fields are never offered), and the `features` list offers `version`, which validation rejects.
- Section 3: completion needs a document that parses. Two common mid-typing states return a parse
  diagnostic and no items.
- Section 4: semantic diagnostics carry no path or range. An unknown field is ranged on its value,
  not its key. YAML syntax errors are a single point.
- Sections 5 and 9: formatting and structured edits drop comments and expand shorthand.
- Section 6: the helpers take text without a file path, so any document with `imports` is
  rejected, even with semantic validation off, although `parse_sdl_file` accepts the same fixture.
- Section 7: no repository example is near the 64 KiB input limit.
- Section 8: field completion uses only the section name. An entry-name position, a nested mapping
  and a scalar value all receive the same list.

## Raw source against the published schema

```text
example files: 21; accepted by rae: 21; with raw-schema errors: 1
  docs/public/_static/examples/first-scenario.sdl.yaml: ["/nodes/lab-network/type: 'Switch' is not one of ['compute', 'switch']"]

accepted by rae (schema errors here are false positives):
  canonical enum value             schema: no errors
  enum value with different case   schema: ["/features/app/type: 'Service' is not one of ['service', 'configuration', 'artifact']"]
  source shorthand string          schema: ["/features/app/source: 'webapp' is not valid under any of the given schemas"]
  infrastructure count shorthand   schema: ["/infrastructure/web: 2 is not of type 'object'"]
  node features list shorthand     schema: ["/nodes/web/features: ['app'] is not of type 'object'"]
  node role string shorthand       schema: ["/nodes/web/roles/client: 'www' is not of type 'object'"]

rejected by rae (schema silence here is a false negative):
  unresolved feature reference     rae: ['sdl.semantic']; schema: no errors
  unknown field                    rae: ['sdl.model.invalid']; schema: ["/nodes/web: Additional properties are not allowed ('colour' was unexpected)"]
  non-canonical key spelling       rae: ['sdl.noncanonical_field']; schema: ["/: Additional properties are not allowed ('Features' was unexpected)"]
  duplicate mapping key            rae: ['sdl.mapping_key_conflict']; schema: no errors
```

The published schema describes the normalized authoring object (`x-raes-validates-raw-source` is
`false`), so shorthand and enum spellings that rae accepts are reported as errors, while errors that
only rae's semantic validation finds are not reported.

## Schema association in yaml-language-server

```text
server: {'name': 'yaml-language-server', 'version': '1.24.0'}
[docs/public/_static/examples/first-scenario.sdl.yaml] ['6:11 Value is not accepted. Valid values: "compute", "switch".']
[accepted case: canonical enum value] no diagnostics
[accepted case: enum value with different case] ['3:15 Value is not accepted. Valid values: "service", "configuration", "artifact".']
[accepted case: source shorthand string] ['3:32 Incorrect type. Expected "Source | null".']
[accepted case: infrastructure count shorthand] ['5:8 Incorrect type. Expected "InfraNode".']
[accepted case: node features list shorthand] ['5:78 Incorrect type. Expected "Features".']
[accepted case: node role string shorthand] ['5:109 Incorrect type. Expected "Role".']
[rejected case: unresolved feature reference] no diagnostics
[rejected case: unknown field] ['5:68 Property colour is not allowed.']
[rejected case: non-canonical key spelling] ['2:1 Property Features is not allowed.']
[rejected case: duplicate mapping key] ['2:1 Map keys must be unique']
examples without diagnostics: 20/21
field completion inside /nodes/web: 15 items: ['architecture', 'asset_value', 'conditions', 'description', 'endpoint_persona', 'features', 'injects', 'os', 'os_distribution', 'os_version', 'resources', 'roles', 'runtime', 'services', 'source']
hover on /nodes/web/type: {"kind": "markdown", "value": "#### NodeType\n\nStructural resource kind, independent of its realization mechanism.\n\nAllowed Values:\n\n* `compute`\n* `switch`\n\nSource: [sdl-authoring-input-v1.json](<bundled schema>)"}
```

The association gives useful completion (15 schema fields under a node, against 9 from the rae
helper) and hover text, but its diagnostics disagree with rae in both directions. One of the 21
accepted repository examples, the quickstart's `first-scenario.sdl.yaml`, shows a false error.

## Latency

Medians on an Apple M3 with 8 cores while other work was running (the load average is printed).
Treat them as indicative.

The rae checkout environment (free-threaded CPython 3.14):

```text
python 3.14.4; load average 13.1; file examples/scenarios/hospital-ransomware-surgery-day.sdl.yaml (46073 bytes)
warm diagnostics: median 354 ms over 5 calls
warm completions: median 277 ms over 5 calls
cold interpreter (import raes + one diagnostics call): median 2064 ms over 3 runs
```

A virtual environment with `raes` 6.0.1 from PyPI (CPython 3.13):

```text
python 3.13.5; load average 11.6; file examples/scenarios/hospital-ransomware-surgery-day.sdl.yaml (46073 bytes)
warm diagnostics: median 283 ms over 5 calls
warm completions: median 279 ms over 5 calls
cold interpreter (import raes + one diagnostics call): median 1695 ms over 3 runs
```

Each helper call parses the whole document again, so a 46 KB scenario costs a few hundred
milliseconds per diagnostics or completion request. The bridge debounces diagnostics for that
reason.
