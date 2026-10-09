"""Validate a single-file, commit-bound on-demand CI request."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess


STAGES = frozenset({
  "RED-testing",
  "temp-testing",
  "GREEN-testing",
  "regression-testing",
  "integration-testing",
})
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class CiInvocationError(ValueError):
  pass


@dataclass(frozen=True)
class CiInvocation:
  stage: str
  previous_tip: str


def parse_invocation(text: str) -> CiInvocation:
  """Parse the exact marker grammar; no implicit default stage."""
  parts = text.removesuffix("\n").split(" ")
  if len(parts) != 2 or parts[0] not in STAGES:
    raise CiInvocationError("invalid CI stage or marker structure")
  if SHA_RE.fullmatch(parts[1]) is None:
    raise CiInvocationError("CI marker requires a full lowercase commit SHA")
  if text != f"{parts[0]} {parts[1]}" and text != (
    f"{parts[0]} {parts[1]}\n"
  ):
    raise CiInvocationError("CI marker must contain exactly one request")
  return CiInvocation(parts[0], parts[1])


def _git(root: Path, *args: str) -> str:
  result = subprocess.run(
    ["git", "-C", str(root), *args],
    capture_output=True,
    text=True,
    check=False,
  )
  if result.returncode:
    raise CiInvocationError(
      f"cannot verify CI invocation commit: {result.stderr.strip()}"
    )
  return result.stdout.strip()


def verify_invocation(root: Path) -> CiInvocation:
  """Require HEAD to be a dedicated request commit on its direct parent."""
  marker = root / ".ci" / "run"
  try:
    requested = parse_invocation(marker.read_text(encoding="utf-8"))
  except OSError as error:
    raise CiInvocationError("missing .ci/run invocation") from error

  parents = _git(root, "rev-list", "--parents", "-n", "1", "HEAD").split()
  if len(parents) != 2:
    raise CiInvocationError("invocation must be a single-parent commit")
  if parents[1] != requested.previous_tip:
    raise CiInvocationError("invocation SHA must equal the prior branch tip")

  changed = _git(
    root,
    "diff-tree",
    "--no-commit-id",
    "--name-only",
    "-r",
    "HEAD",
  ).splitlines()
  if changed != [".ci/run"]:
    raise CiInvocationError("invocation commit must change only .ci/run")
  return requested


def original_candidate(root: Path, tip: str) -> str:
  """Trace verified request/retry and canonical publication commits."""
  if SHA_RE.fullmatch(tip) is None:
    raise CiInvocationError("candidate history requires a full commit SHA")
  sha = tip
  while True:
    parents = _git(root, "rev-list", "--parents", "-n", "1", sha).split()
    if len(parents) != 2:
      return sha
    parent = parents[1]
    changed = _git(
      root, "diff-tree", "--no-commit-id", "--name-only", "-r", sha,
    ).splitlines()
    if changed == [".ci/run"]:
      request = parse_invocation(_git(root, "show", sha + ":.ci/run"))
      if request.previous_tip != parent:
        raise CiInvocationError("historical CI invocation ancestry mismatch")
    elif (len(changed) == 1 and re.fullmatch(
      r"\.repoworkflow/validation/testResults-[1-9][0-9]*\.jsonl",
      changed[0],
    ) and _git(root, "show", "-s", "--format=%s", sha).startswith(
      "test: publish hosted evidence from run "
    )):
      pass
    else:
      return sha
    sha = parent
