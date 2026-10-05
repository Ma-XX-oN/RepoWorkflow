from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import subprocess


class LauncherDiscoveryError(RuntimeError):
  pass


@dataclass(frozen=True)
class RepositoryLauncher:
  repository_root: Path
  launcher: Path
  requires_python: bool


def _run_git(start: Path, *args: str) -> subprocess.CompletedProcess[str]:
  try:
    return subprocess.run(
      ["git", "-C", os.fspath(start), *args],
      capture_output=True,
      text=True,
      check=False,
    )
  except FileNotFoundError as error:
    raise LauncherDiscoveryError(
      "Git is required for repository-local RWF discovery"
    ) from error


def _repository_root(start: Path) -> Path:
  result = _run_git(start, "rev-parse", "--show-toplevel")
  if result.returncode:
    detail = (result.stderr or result.stdout).strip()
    suffix = f": {detail}" if detail else ""
    raise LauncherDiscoveryError(
      f"not inside a suitable Git working tree{suffix}"
    )
  value = result.stdout.strip()
  if not value:
    raise LauncherDiscoveryError("Git did not report a repository root")
  return Path(value).resolve()


def _has_repoworkflow_gitlink(root: Path) -> bool:
  result = _run_git(root, "ls-tree", "HEAD", "--", "RepoWorkflow")
  if result.returncode:
    return False
  fields = result.stdout.strip().split(None, 3)
  return len(fields) >= 3 and fields[0] == "160000" and fields[1] == "commit"


def discover_repository_launcher(start: Path) -> RepositoryLauncher:
  root = _repository_root(Path(start).resolve())

  consumer = root / "scripts" / "repoworkflow.py"
  if consumer.is_file() and _has_repoworkflow_gitlink(root):
    return RepositoryLauncher(root, consumer, True)

  self_launcher = root / "rwf"
  self_engine = root / "repo_workflow.py"
  if self_launcher.is_file() and self_engine.is_file():
    return RepositoryLauncher(root, self_launcher, False)

  raise LauncherDiscoveryError(
    "no repository-local RWF launcher was found; expected "
    "scripts/repoworkflow.py with a pinned RepoWorkflow gitlink or "
    "the RepoWorkflow repository's own rwf launcher"
  )
