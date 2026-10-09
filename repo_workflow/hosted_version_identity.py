"""Hosted request lineage and evidence-backed development-version identity.

No version is invented when a candidate lacks authoritative version evidence.
This helper does not publish tags or perform hosted workflow integration.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_MARKER = re.compile(
  r"(RED|temporary|GREEN|regression|integration)-testing ([0-9a-f]{40})\n?\Z"
)
_VERSION = re.compile(
  r"[0-9]+\.[0-9]+\.[0-9]+-issue\.([1-9][0-9]*)\.[0-9]+\.[0-9]+\Z"
)
_STAGES = {"RED", "temporary", "GREEN", "regression", "integration"}


class HostedVersionError(ValueError):
  pass


def _git(root: Path, *args: str) -> str:
  result = subprocess.run(
    ["git", "-C", str(root), *args], capture_output=True,
    text=True, check=False,
  )
  if result.returncode:
    raise HostedVersionError("cannot verify hosted Git request")
  return result.stdout


def _single_parent(root: Path, sha: str) -> str:
  raw = _git(root, "rev-list", "--parents", "-n", "1", sha).split()
  if len(raw) != 2 or raw[0] != sha:
    raise HostedVersionError("invocation must have one Git parent")
  return raw[1]


def _marker(root: Path, sha: str) -> tuple[str, str] | None:
  path = ".ci/run"
  try:
    raw = _git(root, "show", sha + ":" + path)
  except HostedVersionError:
    return None
  match = _MARKER.fullmatch(raw)
  if match is None:
    raise HostedVersionError("invalid two-field hosted invocation marker")
  return match.group(1), match.group(2)


def resolve_invocation(root: Path, invocation_sha: str) -> dict:
  """Verify marker-only invocation commits and trace retry to source commit."""
  if not isinstance(invocation_sha, str) or not _SHA.fullmatch(invocation_sha):
    raise HostedVersionError("invalid invocation SHA")
  observed: set[str] = set()
  current = invocation_sha
  stage = None
  depth = 0
  while True:
    if current in observed:
      raise HostedVersionError("cyclic invocation lineage")
    observed.add(current)
    marker = _marker(root, current)
    if depth and marker is not None:
      parents = _git(root, "rev-list", "--parents", "-n", "1", current).split()
      if len(parents) != 2:
        raise HostedVersionError("ambiguous candidate history")
      changed = _git(
        root, "diff-tree", "--no-commit-id", "--name-only", "-r",
        parents[1], current,
      ).splitlines()
      if ".ci/run" not in changed:
        marker = None  # The marker is inherited, not a request.
    if marker is None:
      if depth == 0:
        raise HostedVersionError("not a hosted invocation")
      return {
        "invocation_sha": invocation_sha, "request_parent_sha": first_parent,
        "candidate_sha": current, "stage": stage,
        "retry_depth": depth - 1,
      }
    current_stage, recorded = marker
    if current_stage not in _STAGES:
      raise HostedVersionError("unknown hosted stage")
    parent = _single_parent(root, current)
    if recorded != parent:
      raise HostedVersionError("request does not bind immediate parent")
    changes = _git(
      root, "diff-tree", "--no-commit-id", "--name-only", "-r",
      parent, current,
    ).splitlines()
    if changes != [".ci/run"]:
      raise HostedVersionError("invocation changed non-marker inputs")
    if depth == 0:
      stage = current_stage
      first_parent = parent
    elif current_stage != stage:
      raise HostedVersionError("retry changes hosted test stage")
    current = parent
    depth += 1
    if depth > 100:
      raise HostedVersionError("hosted invocation lineage too deep")


def resolve_hosted_version(
  root: Path, invocation_sha: str, canonical_log: Path,
) -> dict:
  """Find one exact original-candidate version, or report absent.

  Only regression/integration terminal results may have a development version.
  A log record is not a version authority unless it binds the same source
  candidate, branch issue and stage; conflicting versions are rejected.
  """
  identity = resolve_invocation(root, invocation_sha)
  identity["test_version"] = None
  if identity["stage"] not in {"regression", "integration"}:
    return identity
  match = re.fullmatch(
    r"testResults-([1-9][0-9]*)\.jsonl", canonical_log.name,
  )
  if (
    match is None
    or canonical_log.is_symlink()
    or canonical_log.resolve() != (
      root.resolve() / ".repoworkflow" / "validation" / canonical_log.name
    )
  ):
    raise HostedVersionError("invalid canonical version-evidence path")
  if not canonical_log.exists():
    return identity
  versions = set()
  for line in canonical_log.read_text(encoding="utf-8").splitlines():
    try:
      record = json.loads(line)
    except ValueError as error:
      raise HostedVersionError("malformed version evidence") from error
    if not isinstance(record, dict):
      raise HostedVersionError("non-object version evidence")
    if record.get("testSHA") != identity["candidate_sha"]:
      continue
    if record.get("kind") != identity["stage"]:
      continue
    version = record.get("testVersion")
    if version is None:
      continue
    if not isinstance(version, str):
      raise HostedVersionError("invalid development version")
    version_match = _VERSION.fullmatch(version)
    if not version_match or version_match.group(1) != match.group(1):
      raise HostedVersionError("version issue does not match results log")
    if record.get("result") not in {"succeeded", "failed", "incomplete"}:
      raise HostedVersionError("version evidence has no valid result")
    source_branch = record.get("branch")
    if not isinstance(source_branch, str) or re.fullmatch(
      "issue-" + match.group(1) + r"(?:-.*)?", source_branch,
    ) is None:
      raise HostedVersionError("version evidence belongs to another branch")
    versions.add(version)
  if len(versions) > 1:
    raise HostedVersionError("conflicting development versions")
  identity["test_version"] = next(iter(versions)) if versions else None
  return identity
