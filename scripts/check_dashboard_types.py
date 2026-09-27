"""Check the dashboard with an existing TypeScript compiler, without downloads."""

from __future__ import annotations

import os
import shutil
import subprocess
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
    compiler = compiler_path()
    script = """
const ts = require(process.argv[1]);
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
        [node, "-e", script, str(compiler)],
        cwd=root,
        check=False,
        timeout=60,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
