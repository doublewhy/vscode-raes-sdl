"""Small SDL documents shared by the evidence probes.

Each document is either accepted by rae's own parser or rejected for one stated reason, so a
probe can compare what rae reports with what a schema-only editor integration reports.
"""

_PROPOSITION = """\
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
    basis: BASIS
    predicate:
      kind: boolean
      property: ready
      semantic_ref: urn:raes:declared-property:ready
      operator: equals
      expected: true
assertions:
  done: {proposition: ok, role: postcondition, polarity: positive}
"""

_NODE = """\
name: demo
features:
  app: {type: FEATURE_TYPE, source: {name: webapp, version: '*'}}
nodes:
  web: {type: compute, os: linux, resources: {ram: 2 GiB, cpu: 1}, features: {FEATURE_REF: client}, roles: {client: {username: www}}}
"""


def _node(feature_type: str = "service", feature_ref: str = "app") -> str:
    return _NODE.replace("FEATURE_TYPE", feature_type).replace("FEATURE_REF", feature_ref)


# rae accepts all of these; a raw-source schema check should report nothing.
ACCEPTED = {
    "canonical enum value": _PROPOSITION.replace("BASIS", "declared_state"),
    "enum value with different case": _node(feature_type="Service"),
    "source shorthand string": _node().replace("source: {name: webapp, version: '*'}", "source: webapp"),
    "infrastructure count shorthand": (
        "name: demo\nnodes:\n  web: {type: compute, os: linux, resources: {ram: 2 GiB, cpu: 1}}\n"
        "infrastructure:\n  web: 2\n"
    ),
    "node features list shorthand": _node().replace("features: {app: client}, roles: {client: {username: www}}", "features: [app]"),
    "node role string shorthand": _node().replace("roles: {client: {username: www}}", "roles: {client: www}"),
}

# rae rejects all of these; the comment names the reason.
REJECTED = {
    "unresolved feature reference": _node(feature_ref="missing"),  # semantic validation
    "unknown field": _node().replace("cpu: 1}", "cpu: 1}, colour: blue"),  # closed model
    "non-canonical key spelling": _node().replace("features:\n  app", "Features:\n  app"),  # strict source profile
    "duplicate mapping key": "name: demo\nname: again\n",  # YAML representation rule
}
