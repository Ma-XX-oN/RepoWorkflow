from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

from .local_guards import LocalGuardError, install_hooks


class InitError(RuntimeError):
  pass


BASH_MARKER = "# RepoWorkflow managed Bash integration v1"
BASHRC_BEGIN = "# >>> RepoWorkflow >>>"
BASHRC_END = "# <<< RepoWorkflow <<<"


@dataclass(frozen=True)
class InitResult:
  root: Path
  shell_file: Path
  hooks: tuple[Path, ...]


def discover_worktree(start: Path) -> Path:
  completed = subprocess.run(
    ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
    text=True,
    capture_output=True,
    check=False,
  )
  if completed.returncode:
    raise InitError("not inside a Git worktree")
  value = completed.stdout.strip()
  if not value:
    raise InitError("cannot determine Git worktree root")
  root = Path(value).resolve()
  if not (root / ".ci" / "repoworkflow.json").is_file():
    raise InitError(
      f"Git worktree is not a RepoWorkflow consumer: {root}"
    )
  return root


def bash_source(engine_root: Path) -> str:
  path = engine_root / "completions" / "repo-workflow.bash"
  try:
    text = path.read_text(encoding="utf-8")
  except FileNotFoundError as exc:
    raise InitError(f"Bash integration template is missing: {path}") from exc
  if not text.startswith(BASH_MARKER + "\n"):
    raise InitError("Bash integration template is not RepoWorkflow-managed")
  return text


def _shell_path(home: Path) -> Path:
  return home / ".config" / "repoworkflow" / "bash" / "repo-workflow.bash"


def _bashrc_block(target: Path) -> str:
  quoted = str(target).replace("'", "'\\''")
  return (
    f"{BASHRC_BEGIN}\n"
    f"[ -r '{quoted}' ] && . '{quoted}'\n"
    f"{BASHRC_END}\n"
  )


def install_bash(
  engine_root: Path,
  *,
  home: Path,
  force: bool = False,
) -> Path:
  source = bash_source(engine_root)
  target = _shell_path(home)
  target.parent.mkdir(parents=True, exist_ok=True)
  if target.exists():
    existing = target.read_text(encoding="utf-8")
    if existing != source and not existing.startswith(BASH_MARKER + "\n") and not force:
      raise InitError(
        f"existing Bash integration is not RepoWorkflow-managed: {target}"
      )
  target.write_text(source, encoding="utf-8", newline="\n")

  bashrc = home / ".bashrc"
  existing_rc = bashrc.read_text(encoding="utf-8") if bashrc.exists() else ""
  begin_count = existing_rc.count(BASHRC_BEGIN)
  end_count = existing_rc.count(BASHRC_END)
  if begin_count != end_count:
    raise InitError(f"malformed RepoWorkflow block in {bashrc}")
  if begin_count == 0:
    separator = "" if not existing_rc or existing_rc.endswith("\n") else "\n"
    bashrc.write_text(
      existing_rc + separator + _bashrc_block(target),
      encoding="utf-8",
      newline="\n",
    )
  elif begin_count > 1:
    raise InitError(f"multiple RepoWorkflow blocks found in {bashrc}")
  return target


def initialize(
  start: Path,
  engine_root: Path,
  *,
  home: Path,
  force: bool = False,
) -> InitResult:
  root = discover_worktree(start.resolve())
  try:
    hooks = tuple(install_hooks(root, force=force))
  except LocalGuardError as exc:
    raise InitError(str(exc)) from exc
  shell_file = install_bash(engine_root.resolve(), home=home.resolve(), force=force)
  return InitResult(root=root, shell_file=shell_file, hooks=hooks)
