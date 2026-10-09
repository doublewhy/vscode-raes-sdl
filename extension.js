'use strict';
// Prototype client: starts the stdio bridge in server/raes_sdl_lsp.py with the configured
// Python interpreter and attaches it to OpenRAE SDL documents. TextMate highlighting, the
// language configuration and the yamlValidation schema association are static contributions
// in package.json and need no code.
const vscode = require('vscode');
const { LanguageClient, TransportKind } = require('vscode-languageclient/node');

let client;

function activate(context) {
  const config = vscode.workspace.getConfiguration('openraeSdl');
  if (!config.get('languageServer.enabled', true)) {
    return undefined;
  }
  const python = config.get('python', 'python3');
  const serverOptions = {
    command: python,
    args: [context.asAbsolutePath('server/raes_sdl_lsp.py')],
    // Run from the extension directory, not the workspace, so nothing in an opened folder
    // becomes the server's working directory.
    options: { cwd: context.extensionPath },
    transport: TransportKind.stdio,
  };
  const clientOptions = {
    // Default mode: *.sdl.yaml opens as `openrae-sdl`. Users who map *.sdl.yaml back to YAML
    // (files.associations) keep the Red Hat YAML extension and still get raes diagnostics.
    documentSelector: [
      { language: 'openrae-sdl' },
      { language: 'yaml', pattern: '**/*.sdl.yaml' },
    ],
  };
  client = new LanguageClient('openraeSdl', 'OpenRAE SDL (raes bridge)', serverOptions, clientOptions);
  return client.start();
}

function deactivate() {
  return client ? client.stop() : undefined;
}

module.exports = { activate, deactivate };
