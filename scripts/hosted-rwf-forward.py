#!/usr/bin/env python3
"""GitHub-hosted adapter for one authenticated numbered RWF invocation.

Provider data is validated here; business command dispatch remains in repo_workflow.py.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys


_CMD = re.compile(r"CMD-[1-9][0-9]*-.+\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")


class HostedForwardError(ValueError):
  pass


def _git(root: Path, *args: str) -> bytes:
  completed = subprocess.run(
    ["git", *args], cwd=root, capture_output=True, check=False,
  )
  if completed.returncode:
    raise HostedForwardError("git " + args[0] + " failed")
  return completed.stdout


def _required(environment: dict[str, str], name: str) -> str:
  value = environment.get(name, "")
  if not value:
    raise HostedForwardError("missing provider context: " + name)
  return value


def authenticated_argv(root: Path, environment: dict[str, str]) -> tuple[str, list[str]]:
  """Validate provider push identity and a canonical committed argv marker."""
  if _required(environment, "GITHUB_EVENT_NAME") != "push":
    raise HostedForwardError("hosted forwarding requires a push event")
  ref = _required(environment, "GITHUB_REF")
  branch = ref.removeprefix("refs/heads/")
  if ref != "refs/heads/" + branch or _CMD.fullmatch(branch) is None:
    raise HostedForwardError("hosted forwarding requires a numbered CMD ref")
  revision = _required(environment, "GITHUB_SHA")
  if _SHA.fullmatch(revision) is None:
    raise HostedForwardError("invalid provider revision")
  repository = _required(environment, "GITHUB_REPOSITORY")
  workflow = _required(environment, "GITHUB_WORKFLOW_REF")
  expected_workflow = (
    repository + "/.github/workflows/remote-rwf.yml@" + ref
  )
  if workflow != expected_workflow:
    raise HostedForwardError("wrong hosted forwarding workflow or ref")
  event_path = Path(_required(environment, "GITHUB_EVENT_PATH"))
  try:
    event = json.loads(event_path.read_text(encoding="utf-8"))
  except (OSError, UnicodeError, ValueError) as exc:
    raise HostedForwardError("invalid provider event JSON") from exc
  if not isinstance(event, dict):
    raise HostedForwardError("provider event must be an object")
  if (
    event.get("ref") != ref
    or event.get("after") != revision
    or event.get("deleted") is True
    or event.get("forced") is True
  ):
    raise HostedForwardError("provider event does not match CMD push")
  provider_repo = event.get("repository")
  if not isinstance(provider_repo, dict) or provider_repo.get("full_name") != repository:
    raise HostedForwardError("provider repository mismatch")
  if _git(root, "rev-parse", "HEAD").decode("ascii").strip() != revision:
    raise HostedForwardError("checkout does not match provider revision")
  parents = _git(root, "rev-list", "--parents", "-n", "1", "HEAD").decode("ascii").split()
  if len(parents) != 2 or parents[0] != revision:
    raise HostedForwardError("CMD request must be a single-parent commit")
  changed = _git(
    root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"
  ).decode("utf-8", errors="strict").splitlines()
  if changed != [".ci/rwf"]:
    raise HostedForwardError("CMD request must modify only .ci/rwf")
  try:
    raw = _git(root, "show", "HEAD:.ci/rwf").decode("utf-8", errors="strict")
    words = shlex.split(raw, posix=True)
  except (UnicodeError, ValueError) as exc:
    raise HostedForwardError("invalid committed argv encoding or quoting") from exc
  if raw != shlex.join(words) + "\n":
    raise HostedForwardError("noncanonical committed .ci/rwf")
  if len(words) < 3 or words[-2] != "--remote" or re.fullmatch(r"0|[1-9][0-9]*", words[-1]) is None:
    raise HostedForwardError("CMD argument file lacks numbered --remote suffix")
  return branch, words


def run(root: Path, environment: dict[str, str]) -> int:
  branch, words = authenticated_argv(root, environment)
  # git checkout pins the provider SHA; retain the named branch for the wrapper.
  _git(root, "switch", "-c", branch)
  if _git(root, "symbolic-ref", "--short", "HEAD").decode("utf-8").strip() != branch:
    raise HostedForwardError("CMD branch identity was not restored")
  invoked_env = dict(environment)
  invoked_env["RWF_HOSTED_INVOCATION"] = "1"
  result = subprocess.run(
    [sys.executable, str(root / "repo_workflow.py"), "--root", str(root), *words],
    cwd=root, env=invoked_env, stdin=subprocess.DEVNULL, check=False,
  )
  return result.returncode


def main() -> int:
  try:
    return run(Path.cwd(), dict(os.environ))
  except (HostedForwardError, OSError, UnicodeError) as exc:
    print("RepoWorkflow hosted forwarding error: " + str(exc), file=sys.stderr)
    return 2


if __name__ == "__main__":
  raise SystemExit(main())
