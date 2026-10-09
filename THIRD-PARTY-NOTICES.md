# Third-party notices

## OpenRAE/rae authoring schema

`schemas/sdl-authoring-input-v1.json` is an unmodified copy of
`contracts/schemas/sdl/sdl-authoring-input-v1.json` from
[OpenRAE/rae](https://github.com/OpenRAE/rae) at commit
`35122105b0c1bb648754625d8e3920eafa9bc599`, distributed under this license:

```text
MIT License

Copyright (c) 2026 Brad Edwards

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Not redistributed

- `test/grammar.test.mjs` downloads VS Code's YAML grammars (MIT, Microsoft Corporation) from the
  `microsoft/vscode` repository at test time, checks their SHA-256 digests and caches them in the
  ignored `.cache/` directory.
- npm dependencies are installed from the registry by `npm ci` and keep their own license files
  under `node_modules/`. The runtime dependency is `vscode-languageclient` (MIT).
