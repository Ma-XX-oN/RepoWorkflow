"""Prepare an explicit engine-self version before a hosted marker request."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess

from .engine_version_adapter import (
  EngineVersionError, read_engine_version, transition_engine_version,
)
from .phase_terminal import plan_phase, PhaseTransitionError


class EnginePreparationError(ValueError):
  pass


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
  result = subprocess.run(
    ["git", "-C", str(root), *args], capture_output=True,
    text=True, check=False,
  )
  if check and result.returncode:
    raise EnginePreparationError("engine Git preparation failed: " + args[0])
  return result


def _remote_tag(root: Path, remote: str, tag: str) -> bool:
  output = _git(root, "ls-remote", "--tags", remote,
                "refs/tags/" + tag).stdout.strip()
  local = _git(root, "show-ref", "--verify", "--quiet",
               "refs/tags/" + tag, check=False)
  if local.returncode not in {0, 1}:
    raise EnginePreparationError("cannot verify local development terminal tag")
  return bool(output) or local.returncode == 0


def prepare_engine_request(
  root: Path, *, stage: str, issue: int, remote: str = "origin",
) -> str:
  """Commit a repo-owned version transition before .ci/run, or replay it."""
  if stage not in {"regression", "integration"}:
    raise EnginePreparationError("only terminal phases need version preparation")
  if isinstance(issue, bool) or not isinstance(issue, int) or issue < 1:
    raise EnginePreparationError("invalid issue identity")
  if not re.fullmatch(r"issue-" + str(issue) + r"(?:-.*)?",
                      _git(root, "branch", "--show-current").stdout.strip()):
    raise EnginePreparationError("issue branch differs from version authority")
  before = read_engine_version(root)
  stable = re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", before)
  if stable:
    transition_engine_version(root, operation="task --issue", issue=issue)
  else:
    match = re.fullmatch(
      r"[0-9]+\.[0-9]+\.[0-9]+-issue\.([1-9][0-9]*)\.[0-9]+\.(0|[1-9][0-9]*)",
      before,
    )
    if match is None or int(match.group(1)) != issue:
      raise EnginePreparationError("development version belongs to another issue")
    version = before
    if _remote_tag(root, remote, plan_phase(
      version, phase="integration", outcome="FAIL",
    ).terminal_tag):
      transition_engine_version(
        root, operation="task --increment merge-integration-failed",
      )
    elif (
      (stage == "regression" and any(_remote_tag(
        root, remote, plan_phase(version, phase=phase, outcome=outcome).terminal_tag,
      ) for phase, outcome in (("regression", "FAIL"), ("integration", "PASS"))))
      or (stage == "integration" and any(_remote_tag(
        root, remote, plan_phase(version, phase=phase, outcome="PASS").terminal_tag,
      ) for phase in ("regression", "integration")))
    ):
      transition_engine_version(
        root, operation="task --increment CI-iteration",
      )
  version = read_engine_version(root)
  if version != before:
    _git(root, "add", "--", ".ci/engine-version")
    _git(root, "commit", "--only", "-m",
         "chore(test): prepare engine development version " + version,
         "--", ".ci/engine-version")
  return version
