// Tokenize SDL with this extension's grammar layered on VS Code's own YAML grammar.
// The YAML grammar files are fetched once from the VS Code 1.140.0 tag (commit pinned below),
// verified by SHA-256, and cached in .cache/. Set VSCODE_YAML_SYNTAXES to a directory that
// already holds them (for example an installed VS Code's extensions/yaml/syntaxes) to run offline.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import oniguruma from 'vscode-oniguruma';
import vsctm from 'vscode-textmate';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const VSCODE_COMMIT = '07f806f999227108933c2e30515b26eecc1fda74'; // tag 1.140.0
const YAML_GRAMMARS = {
  'source.yaml': ['yaml.tmLanguage.json', '17f25b037d082408b3ac7af5bb53e94125cc1a47857a75da451d6ea4ac0602df'],
  'source.yaml.1.2': ['yaml-1.2.tmLanguage.json', '1e62af3f7ccccce7ed45b4ee4f3d8461b7e9c3bee42d40b0057934ba6dd62f80'],
  'source.yaml.1.3': ['yaml-1.3.tmLanguage.json', '4d2eb8e4139b82a610e4f02a0f663ebbb183d4d5e97b3f098a5a844f4efcf6b0'],
  'source.yaml.1.1': ['yaml-1.1.tmLanguage.json', '577102ecafb5a6fe88b766ceed020c2cc32aa16f82556ae36385f23f7b834963'],
  'source.yaml.1.0': ['yaml-1.0.tmLanguage.json', '6e521c226b702f17fca01ee380479e77350ac754fc4bc127d997ab52c140bd1e'],
  'source.yaml.embedded': ['yaml-embedded.tmLanguage.json', 'b63b60dfef3237d9c51c7dfd2a488735ecc8e22fdb1a0e8fa8b34d2f77bf873e'],
};
const SDL_GRAMMAR = path.join(root, 'syntaxes', 'openrae-sdl.tmLanguage.json');
const SECTION = 'support.type.section.openrae-sdl';
const METADATA = 'support.type.metadata.openrae-sdl';
const PLACEHOLDER = 'variable.other.placeholder.openrae-sdl';

async function yamlGrammarText(file, sha256) {
  const local = process.env.VSCODE_YAML_SYNTAXES;
  const cacheDir = path.join(root, '.cache', 'vscode-yaml-1.140.0');
  const cached = path.join(local || cacheDir, file);
  let text;
  if (fs.existsSync(cached)) {
    text = fs.readFileSync(cached, 'utf8');
  } else {
    const url = `https://raw.githubusercontent.com/microsoft/vscode/${VSCODE_COMMIT}/extensions/yaml/syntaxes/${file}`;
    const response = await fetch(url);
    assert.equal(response.status, 200, `download ${url}`);
    text = await response.text();
    fs.mkdirSync(cacheDir, { recursive: true });
    fs.writeFileSync(path.join(cacheDir, file), text);
  }
  if (!local) {
    assert.equal(createHash('sha256').update(text).digest('hex'), sha256, `${file} does not match the pinned VS Code grammar`);
  }
  return text;
}

async function loadGrammar() {
  const wasm = fs.readFileSync(path.join(root, 'node_modules', 'vscode-oniguruma', 'release', 'onig.wasm')).buffer;
  await oniguruma.loadWASM(wasm);
  const registry = new vsctm.Registry({
    onigLib: Promise.resolve({
      createOnigScanner: (sources) => new oniguruma.OnigScanner(sources),
      createOnigString: (value) => new oniguruma.OnigString(value),
    }),
    loadGrammar: async (scopeName) => {
      if (scopeName === 'source.openrae-sdl') {
        return vsctm.parseRawGrammar(fs.readFileSync(SDL_GRAMMAR, 'utf8'), SDL_GRAMMAR);
      }
      const entry = YAML_GRAMMARS[scopeName];
      return entry ? vsctm.parseRawGrammar(await yamlGrammarText(...entry), `${entry[0]}`) : null;
    },
  });
  return registry.loadGrammar('source.openrae-sdl');
}

function tokenize(grammar, text) {
  const tokens = [];
  let state = vsctm.INITIAL;
  text.split('\n').forEach((line, lineNumber) => {
    const result = grammar.tokenizeLine(line, state);
    for (const token of result.tokens) {
      tokens.push({ line: lineNumber, text: line.slice(token.startIndex, token.endIndex), scopes: token.scopes });
    }
    state = result.ruleStack;
  });
  return tokens;
}

function scopesOf(tokens, line, text) {
  const token = tokens.find((candidate) => candidate.line === line && candidate.text === text);
  assert.ok(token, `no token ${JSON.stringify(text)} on line ${line}`);
  return token.scopes;
}

const SAMPLE = [
  'name: demo', // 0
  '# nodes: a comment, not a key', // 1
  'nodes:', // 2
  '  web:', // 3
  '    type: compute', // 4
  '    features: [app]', // 5
  '    description: |', // 6
  '      nodes: inside a block scalar', // 7
  'infrastructure:', // 8
  '  web: {count: "${replicas}", links: [lab-network]}', // 9
  'features:', // 10
  '  app: {type: service, source: "pkg-${version}", destination: ${Not_A_Var}}', // 11
  'variables:', // 12
  '  replicas: {type: integer, default: ${replicas}}', // 13
].join('\n');

const grammar = await loadGrammar();
const tokens = tokenize(grammar, SAMPLE);

test('top-level SDL sections keep their YAML key scope and gain the section scope', () => {
  for (const [line, key] of [[2, 'nodes'], [8, 'infrastructure'], [10, 'features'], [12, 'variables']]) {
    const scopes = scopesOf(tokens, line, key);
    assert.ok(scopes.includes('entity.name.tag.yaml'), `${key} lost its YAML key scope`);
    assert.ok(scopes.includes(SECTION), `${key} is not marked as an SDL section`);
  }
});

test('document metadata keys are marked separately', () => {
  assert.ok(scopesOf(tokens, 0, 'name').includes(METADATA));
});

test('nested keys, comments and block scalars are not marked as sections', () => {
  const nested = scopesOf(tokens, 5, 'features');
  assert.ok(nested.includes('entity.name.tag.yaml'));
  assert.ok(!nested.includes(SECTION));
  for (const token of tokens.filter((candidate) => candidate.line === 1 || candidate.line === 7)) {
    assert.ok(!token.scopes.includes(SECTION), `${JSON.stringify(token.text)} marked as a section`);
  }
});

test('variable placeholders are marked in quoted and plain scalars', () => {
  assert.ok(scopesOf(tokens, 9, '${replicas}').includes(PLACEHOLDER));
  assert.ok(scopesOf(tokens, 11, '${version}').includes(PLACEHOLDER));
  assert.ok(scopesOf(tokens, 13, '${replicas}').includes(PLACEHOLDER));
});

test('text that does not match the variable name pattern is left alone', () => {
  const marked = tokens.filter((token) => token.line === 11 && token.scopes.includes(PLACEHOLDER)).map((token) => token.text);
  assert.deepEqual(marked, ['${version}']);
});

test('section names match the top-level properties of the bundled authoring schema', () => {
  const schema = JSON.parse(fs.readFileSync(path.join(root, 'schemas', 'sdl-authoring-input-v1.json'), 'utf8'));
  const raw = JSON.parse(fs.readFileSync(SDL_GRAMMAR, 'utf8'));
  const names = (rule) => rule.match.slice('^(?:'.length, rule.match.indexOf(')')).split('|');
  const grammarKeys = [...names(raw.repository['section-key']), ...names(raw.repository['metadata-key'])].sort();
  assert.deepEqual(grammarKeys, Object.keys(schema.properties).sort());
});
