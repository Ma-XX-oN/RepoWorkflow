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
  r"(RED|temp|GREEN|regression|integration)-testing ([0-9a-f]{40})\n?\Z"
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
  # Absence is established by the Git tree, not by suppressing read failures.
  entries = _git(root, "ls-tree", "-z", sha, "--", ".ci/run")
  if not entries:
    return None
  if entries.count("\0") != 1 or not entries.endswith("\0"):
    raise HostedVersionError("ambiguous hosted marker tree entry")
  header, separator, pathname = entries[:-1].partition("\t")
  if (
    separator != "\t" or pathname != ".ci/run"
    or not header.startswith("100644 blob ")
  ):
    raise HostedVersionError("hosted invocation marker must be regular file")
  raw = _git(root, "show", sha + ":.ci/run")
  match = _MARKER.fullmatch(raw)
  if match is None:
    raise HostedVersionError("invalid two-field hosted invocation marker")
  stage = "temporary" if match.group(1) == "temp" else match.group(1)
  return stage, match.group(2)


def resolve_invocation(root: Path, invocation_sha: str) -> dict:
  """Verify marker-only invocation commits and trace retry to source commit."""
  if not isinstance(invocation_sha, str) or not _SHA.fullmatch(invocation_sha):
    raise HostedVersionError("invalid invocation SHA")
  observed: set[str] = set()
  current = invocation_sha
  stage = None
  depth = 0
  same_stage_retries = 0
  transitions = 0
  while True:
    if current in observed:
      raise HostedVersionError("cyclic invocation lineage")
    observed.add(current)
    marker = _marker(root, current)
    if depth and marker is not None:
      parents = _git(root, "rev-list", "--parents", "-n", "1", current).split()
      if len(parents) < 2 or parents[0] != current:
        # Root commits can contain a marker but are never retry commits.
        marker = None
      else:
        changed = _git(
          root, "diff-tree", "--no-commit-id", "--name-only", "-r",
          parents[1], current,
        ).splitlines()
        if ".ci/run" not in changed:
          marker = None  # An inherited marker does not make a request.
        elif len(parents) != 2:
          raise HostedVersionError("marker-changing merge cannot be a request")
    if marker is None:
      if depth == 0:
        raise HostedVersionError("not a hosted invocation")
      return {
        "invocation_sha": invocation_sha, "request_parent_sha": first_parent,
        "candidate_sha": current, "stage": stage,
        "retry_depth": same_stage_retries,
        "stage_transition_count": transitions,
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
    elif current_stage == stage and transitions == 0:
      same_stage_retries += 1
    elif current_stage != stage:
      transitions += 1
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
  version_owners: dict[str, tuple[str, str]] = {}
  terminal_outcomes: dict[str, str] = {}
  try:
    lines = canonical_log.read_text(encoding="utf-8").splitlines()
  except (OSError, UnicodeError) as error:
    raise HostedVersionError("cannot read canonical version evidence") from error
  for line in lines:
    try:
      record = json.loads(line)
    except ValueError as error:
      raise HostedVersionError("malformed version evidence") from error
    if not isinstance(record, dict):
      raise HostedVersionError("non-object version evidence")
    kind = record.get("kind")
    if kind not in {"regression", "integration"}:
      continue
    version = record.get("testVersion")
    if version is None:
      continue
    if not isinstance(version, str):
      raise HostedVersionError("invalid development version")
    version_match = _VERSION.fullmatch(version)
    if not version_match or version_match.group(1) != match.group(1):
      raise HostedVersionError("version issue does not match results log")
    owner = (record.get("testSHA"), kind)
    if not isinstance(owner[0], str) or not _SHA.fullmatch(owner[0]):
      raise HostedVersionError("invalid version candidate identity")
    if record.get("result") not in {"succeeded", "failed", "incomplete"}:
      raise HostedVersionError("version evidence has no valid result")
    if record.get("result") == "incomplete":
      continue  # No terminal allocation and no version consumed.
    prior = version_owners.get(version)
    if prior is not None and prior != owner:
      raise HostedVersionError("version evidence claimed by different candidate or phase")
    version_owners[version] = owner
    terminal_result = record["result"]
    earlier_result = terminal_outcomes.get(version)
    if earlier_result is not None and earlier_result != terminal_result:
      raise HostedVersionError("conflicting terminal version outcomes")
    terminal_outcomes[version] = terminal_result
    if owner[0] != identity["candidate_sha"]:
      continue
    source_branch = record.get("branch")
    if not isinstance(source_branch, str) or re.fullmatch(
      "issue-" + match.group(1) + r"(?:-.*)?", source_branch,
    ) is None:
      raise HostedVersionError("version evidence belongs to another branch")
    if kind != identity["stage"]:
      continue
    if record.get("headChangedDuringTest") is not False:
      raise HostedVersionError("version evidence candidate moved during test")
    if record.get("uncommittedChanges") != []:
      raise HostedVersionError("version evidence used dirty inputs")
    versions.add(version)
  if len(versions) > 1:
    raise HostedVersionError("conflicting development versions")
  identity["test_version"] = next(iter(versions)) if versions else None
  return identity
