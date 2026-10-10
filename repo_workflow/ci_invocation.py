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
  # Verify the committed request, never mutable working-tree contents.
  requested = parse_invocation(_git(root, "show", "HEAD:.ci/run") + "\n")

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
