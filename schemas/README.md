# Bundled schema

`sdl-authoring-input-v1.json` is an unmodified copy of
[`contracts/schemas/sdl/sdl-authoring-input-v1.json`](https://github.com/OpenRAE/rae/blob/35122105b0c1bb648754625d8e3920eafa9bc599/contracts/schemas/sdl/sdl-authoring-input-v1.json)
from OpenRAE/rae at commit `35122105b0c1bb648754625d8e3920eafa9bc599` (the `dev` branch on 2026-10-08).

- SHA-256: `162121460f19a555f4e7c469a3e4574fe4ed5ecabe628836bf1880ede5f1aba0`
- License: MIT, Copyright (c) 2026 Brad Edwards. The full notice is in
  [`../THIRD-PARTY-NOTICES.md`](../THIRD-PARTY-NOTICES.md).

It is bundled because the schema's `$id`
(`https://openrae.github.io/rae/schemas/sdl-authoring-input-v1.json`) returned HTTP 404 on
2026-10-09, and because an editor association should work offline.

A bundled copy pins one rae revision. The `raes` 6.0.1 wheel on PyPI ships a different copy
(SHA-256 `ad7285715465e170d9cc47825847a71cd4e73693d235379ad39a0e9ff7a4de41`, reachable through
`raes_contracts.corpus.corpus_family_root("schemas")`): this copy adds the top-level
`execution_policy` section and four `$defs` entries that the release does not have. An author
whose interpreter has `raes` 6.0.1 is therefore offered `execution_policy`, which that `raes`
rejects:

```console
$ python3 -m venv /tmp/raes-6.0.1 && /tmp/raes-6.0.1/bin/pip install -q raes==6.0.1
$ /tmp/raes-6.0.1/bin/python -c 'from raes.language_service import language_diagnostics as d; print(d("name: demo\nexecution_policy: {}\n")["diagnostics"][0]["message"])'
Extra inputs are not permitted
```

The schema describes the **normalized authoring object**, not raw YAML source: its
`x-raes-validates-raw-source` annotation is `false`. Raw-source shorthand and case-insensitive enum
values that rae accepts are therefore reported as schema errors. See the main README and
[`../evidence/README.md`](../evidence/README.md) for the measured effect.
