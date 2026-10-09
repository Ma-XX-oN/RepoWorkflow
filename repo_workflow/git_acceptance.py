"""Atomic Git destination updates for validated integration candidates.

This transport enforces an expected-SHA lease at the remote ref update.
A lease is not a substitute for protected-server rules or merge authorisation.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .pre_merge_gate import PreMergeGateError, accept_pre_merge_candidate


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REF = re.compile(r"refs/heads/[A-Za-z0-9][A-Za-z0-9._/-]*\Z")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
  return subprocess.run(
    ["git", "-C", str(root), *args],
    text=True, capture_output=True, check=False,
  )


def _check_target(ref: str) -> None:
  if (
    not _REF.fullmatch(ref)
    or ".." in ref or "//" in ref or "@{" in ref
    or ref.endswith((".", "/", ".lock"))
    or any(part.startswith(".") or part.endswith(".")
           for part in ref.split("/"))
  ):
    raise PreMergeGateError("integration blocked: invalid destination ref")


def read_remote_tip(root: Path, remote: str, ref: str) -> str:
  """Read an exact remote branch ref without accepting ambiguous output."""
  _check_target(ref)
  if not remote or remote.startswith("-"):
    raise PreMergeGateError("integration blocked: invalid remote")
  result = _git(root, "ls-remote", "--exit-code", remote, ref)
  if result.returncode:
    raise PreMergeGateError("integration blocked: destination unavailable")
  lines = result.stdout.splitlines()
  if len(lines) != 1:
    raise PreMergeGateError("integration blocked: ambiguous destination")
  fields = lines[0].split("\t")
  if len(fields) != 2 or fields[1] != ref or not _SHA.fullmatch(fields[0]):
    raise PreMergeGateError("integration blocked: invalid destination response")
  return fields[0]


def push_if_parent(
  root: Path, remote: str, ref: str, candidate: str, expected: str,
) -> bool:
  """Atomically update a remote ref only when its current SHA is expected.

  Uses Git's explicit force-with-lease compare-and-swap. It deliberately
  forbids push negotiation, implicit tracking refs and deletion. The caller
  must separately ensure server-side authorization and protection.
  """
  _check_target(ref)
  if not remote or remote.startswith("-"):
    raise PreMergeGateError("integration blocked: invalid remote")
  if not all(isinstance(value, str) and _SHA.fullmatch(value)
             for value in (candidate, expected)):
    raise PreMergeGateError("integration blocked: invalid acceptance SHA")
  result = _git(
    root, "push", "--porcelain",
    "--force-with-lease=" + ref + ":" + expected,
    remote, candidate + ":" + ref,
  )
  if result.returncode == 0:
    return True
  # Do not claim that any failed push is specifically a lost lease.
  raise PreMergeGateError(
    "integration blocked: remote rejected atomic acceptance"
  )


def accept_git_candidate(
  root: Path,
  *,
  remote: str,
  destination_ref: str,
  candidate_sha: str,
  recorded_parent_tip: str,
  server_protection_verified: bool,
  results_dir: Path,
  config: dict,
  version: str,
  canonical_log: Path,
  required_platforms: tuple[str, ...],
  provider_repo: str | None = None,
) -> None:
  """Run evidence preflight and CAS for an explicitly authorised integration."""
  if server_protection_verified is not True:
    raise PreMergeGateError(
      "integration blocked: server protection is not verified"
    )
  _check_target(destination_ref)
  if destination_ref == "refs/heads/main":
    raise PreMergeGateError(
      "integration blocked: protected main requires the GitHub PR merge gate"
    )
  accept_pre_merge_candidate(
    root,
    candidate_sha=candidate_sha,
    recorded_parent_tip=recorded_parent_tip,
    read_authoritative_parent_tip=lambda: read_remote_tip(
      root, remote, destination_ref,
    ),
    accept_if_parent=lambda candidate, expected: push_if_parent(
      root, remote, destination_ref, candidate, expected,
    ),
    results_dir=results_dir,
    config=config,
    version=version,
    canonical_log=canonical_log,
    required_platforms=required_platforms,
    provider_repo=provider_repo,
  )
