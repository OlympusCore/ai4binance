"""Check the dashboard with an existing TypeScript compiler, without downloads."""

from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
from pathlib import Path


def compiler_path() -> Path:
    """Resolve an explicitly configured compiler or the installed editor compiler."""
    configured = os.environ.get("AI4BINANCE_TYPESCRIPT_PATH")
    if configured:
        candidate = Path(configured)
        if not candidate.is_file():
            raise RuntimeError("DASHBOARD_TYPESCRIPT_COMPILER_UNAVAILABLE")
        return candidate.resolve()
    command = shutil.which("tsc")
    if command:
        candidate = Path(command).resolve().parent.parent / "lib/typescript.js"
        if candidate.is_file():
            return candidate
    roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Microsoft VS Code",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft VS Code",
    ]
    for root in roots:
        matches = sorted(
            root.glob(
                "*/resources/app/extensions/node_modules/typescript/lib/typescript.js"
            )
        )
        if matches:
            return matches[-1]
    raise RuntimeError(
        "DASHBOARD_TYPESCRIPT_COMPILER_UNAVAILABLE: set AI4BINANCE_TYPESCRIPT_PATH"
    )


def main() -> int:
    """Run strict no-emit checking on the canonical interface sources."""
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("DASHBOARD_NODE_UNAVAILABLE")
    root = Path(__file__).resolve().parents[1]
    pins = tomllib.loads(
        (root / "config/interface/dashboard_toolchain.toml").read_text(encoding="utf-8")
    )
    compiler = compiler_path()
    script = """
const ts = require(process.argv[1]);
if (process.versions.node !== process.argv[2] || ts.version !== process.argv[3]) {
  throw new Error('DASHBOARD_TOOLCHAIN_VERSION_MISMATCH');
}
const config = ts.readConfigFile('frontend/tsconfig.json', ts.sys.readFile);
if (config.error) throw new Error(
  ts.flattenDiagnosticMessageText(config.error.messageText, '\\n'));
const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, 'frontend');
const diagnostics = [...parsed.errors];
// Adapters share a packaged closure, but expose explicit independent type contracts.
for (const file of parsed.fileNames) {
  const program = ts.createProgram([file], parsed.options);
  diagnostics.push(...ts.getPreEmitDiagnostics(program));
}
// Also check the actual shared closure: local declarations cannot conceal
// incompatible signatures between the typed shell and its typed adapters.
function parts(name) {
  const text = ts.sys.readFile('frontend/src/' + name);
  const source = ts.createSourceFile(name, text, parsed.options.target, true);
  const result = {declarations: [], types: [], body: []};
  for (const statement of source.statements) {
    const declared = statement.modifiers?.some(
      m => m.kind === ts.SyntaxKind.DeclareKeyword);
    const target = declared ? result.declarations :
      ts.isInterfaceDeclaration(statement)
        ? result.types : result.body;
    target.push(statement.getFullText(source));
  }
  return result;
}
const shell = parts('dashboard_shell.ts');
const adapter = parts('command_center.ts');
const external = adapter.declarations.filter(text =>
  !/declare (?:const (?:root|state)\\b|function (?:render|go)\\b)/.test(text));
const combined = ts.sys.readFile('frontend/src/dashboard_icons.ts') + '\\n' +
  adapter.types.join('\\n') + '\\n' + external.join('\\n') +
  '\\ndeclare function pollLocal(): Promise<void>;\\n' + shell.types.join('\\n') +
  shell.body.join('\\n').replace('// @dashboard-adapters', adapter.body.join('\\n'));
const paths = require('node:path');
const virtual = paths.resolve('frontend/dashboard-composed.ts')
  .split(paths.sep).join('/');
const host = ts.createCompilerHost(parsed.options);
const getSourceFile = host.getSourceFile.bind(host);
host.getSourceFile = (name, target, onError, shouldCreate) => name === virtual
  ? ts.createSourceFile(name, combined, target, true)
  : getSourceFile(name, target, onError, shouldCreate);
diagnostics.push(...ts.getPreEmitDiagnostics(
  ts.createProgram([virtual], parsed.options, host)));
for (const item of diagnostics) {
  const line = item.file && item.start !== undefined
    ? item.file.getLineAndCharacterOfPosition(item.start).line + 1 : '';
  const location = item.file ? item.file.fileName + ':' + line : '';
  console.error(location, ts.flattenDiagnosticMessageText(item.messageText, '\\n'));
}
console.log(JSON.stringify({compiler:ts.version, files:parsed.fileNames.length,
  diagnostics:diagnostics.length}));
process.exitCode = diagnostics.length ? 1 : 0;
"""
    completed = subprocess.run(  # noqa: S603
        [node, "-e", script, str(compiler), pins["node"], pins["typescript"]],
        cwd=root,
        check=False,
        timeout=60,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
