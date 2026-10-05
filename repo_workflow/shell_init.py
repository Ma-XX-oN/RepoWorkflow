from __future__ import annotations

from pathlib import Path
import os
import shlex

from .launcher_discovery import (
  LauncherDiscoveryError,
  discover_repository_launcher,
)


def _bash_path(path: Path) -> str:
  value = path.resolve().as_posix()
  if os.name == "nt" and len(value) >= 3 and value[1:3] == ":/":
    value = f"/{value[0].lower()}{value[2:]}"
  return value


def _bash_literal(path: Path) -> str:
  return shlex.quote(_bash_path(path))


def _argument_literal(path: Path) -> str:
  return shlex.quote(path.resolve().as_posix())


def _consumer_function(launcher: Path) -> str:
  target = _argument_literal(launcher)
  return "\n".join([
    "rwf() {",
    "  local _rwf_python",
    "  for _rwf_python in python3 python; do",
    "    if command -v \"$_rwf_python\" >/dev/null 2>&1 &&",
    "       \"$_rwf_python\" -c 'import sys; raise SystemExit(0 if sys.version_info.major == 3 else 1)' \\",
    "         >/dev/null 2>&1; then",
    f"      \"$_rwf_python\" {target} \"$@\"",
    "      return $?",
    "    fi",
    "  done",
    "  printf '%s\\n' \"rwf: Python 3 is required; install Python 3 and ensure 'python3' or 'python' is on PATH.\" >&2",
    "  return 127",
    "}",
  ])


def _self_function(root: Path, launcher: Path) -> str:
  return "\n".join([
    "rwf() {",
    f"  {_bash_literal(launcher)} --root {_argument_literal(root)} \"$@\"",
    "}",
  ])


def render_bash_init(root: Path, engine_root: Path) -> str:
  try:
    discovery = discover_repository_launcher(root)
  except LauncherDiscoveryError as error:
    raise ValueError(str(error)) from error

  completion_path = engine_root / "completions" / "repo-workflow.bash"
  if not completion_path.is_file():
    raise ValueError(f"Bash completion source is missing: {completion_path}")

  command_function = (
    _consumer_function(discovery.launcher)
    if discovery.requires_python
    else _self_function(discovery.repository_root, discovery.launcher)
  )
  completion = completion_path.read_text(encoding="utf-8").rstrip("\n")
  lines = [
    "# RepoWorkflow Bash initialization.",
    "unalias rwf repo-workflow 2>/dev/null || true",
    f"REPO_WORKFLOW_ROOT={_argument_literal(discovery.repository_root)}",
    "REPO_WORKFLOW_COMMAND=rwf",
    "",
    command_function,
    "",
    'repo-workflow() { rwf "$@"; }',
    "",
    completion,
    "",
    "# To activate this Bash initialization portably, run:",
    '#   source /dev/stdin <<<"$(rwf init bash)"',
    "# On Bash 4+ this shorter form is also supported:",
    "#   source <(rwf init bash)",
    "# Equivalent portable dot form:",
    '#   . /dev/stdin <<<"$(rwf init bash)"',
  ]
  return "\n".join(lines) + "\n"
