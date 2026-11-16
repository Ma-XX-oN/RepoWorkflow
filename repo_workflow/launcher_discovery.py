from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from .git import GitError, git_bytes


class LauncherDiscoveryError(RuntimeError):
  pass


@dataclass(frozen=True)
class RepositoryLauncher:
  repository_root: Path
  launcher: Path
  requires_python: bool


def _run_git(start: Path, *args: str) -> subprocess.CompletedProcess[str]:
  try:
    result = git_bytes(start, *args, check=False)
    stdout = result.stdout.decode("utf-8", "strict")
    stderr = result.stderr.decode("utf-8", "strict")
  except (GitError, UnicodeError) as error:
    raise LauncherDiscoveryError("invalid Git launcher discovery protocol") from error
  return subprocess.CompletedProcess(result.args, result.returncode, stdout, stderr)


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
  result = _run_git(root, "rev-parse", "--verify", "HEAD:RepoWorkflow")
  return result.returncode == 0 and bool(result.stdout.strip())


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
