"""Read-only pre-merge candidate and test-result checks.

This is a local gate component, not an atomic server merge protection.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable
import re
import subprocess

from .results import collect_results, evaluate_results
from .github_evidence import verify_hosted_integration
from .test_evidence_gate import (
  CanonicalEvidenceError, require_integration_evidence,
)


_SHA = re.compile(r"^[0-9a-f]{40}$")


class PreMergeGateError(RuntimeError):
  pass


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
  return subprocess.run(
    ["git", "-C", str(root), *args],
    capture_output=True,
    text=True,
    check=False,
  )


def check_pre_merge_candidate(
  root: Path,
  *,
  candidate_sha: str,
  recorded_parent_tip: str,
  authoritative_parent_tip: str,
  results_dir: Path,
  config: dict,
  version: str,
  canonical_log: Path,
  required_platforms: tuple[str, ...],
  verify_hosted: Callable[[dict], bool] | None = None,
  provider_repo: str | None = None,
) -> None:
  """Check facts without changing repository state.

  The caller must independently authenticate the authoritative parent tip and
  the origin/integrity of results_dir. Server rules must repeat the freshness
  check atomically at merge acceptance; a local preflight cannot close races.
  """
  for label, value in (
    ("candidate", candidate_sha),
    ("recorded parent", recorded_parent_tip),
    ("authoritative parent", authoritative_parent_tip),
  ):
    if _SHA.fullmatch(value) is None:
      raise PreMergeGateError(f"invalid {label} SHA")

  if recorded_parent_tip != authoritative_parent_tip:
    raise PreMergeGateError("integration blocked: destination tip advanced")

  actual = _git(root, "rev-parse", "HEAD")
  if actual.returncode or actual.stdout.strip() != candidate_sha:
    raise PreMergeGateError("integration blocked: candidate SHA changed")

  ancestry = _git(
    root,
    "merge-base",
    "--is-ancestor",
    recorded_parent_tip,
    candidate_sha,
  )
  if ancestry.returncode:
    raise PreMergeGateError("integration blocked: candidate excludes parent tip")

  try:
    if verify_hosted is None and provider_repo is not None:
      verify_hosted = lambda record: verify_hosted_integration(
        record, repo=provider_repo,
      )
    require_integration_evidence(
      canonical_log,
      candidate=candidate_sha,
      required_platforms=required_platforms,
      verify_hosted=verify_hosted,
    )
  except CanonicalEvidenceError as error:
    raise PreMergeGateError(
      "integration blocked: " + str(error)
    ) from error

  outcome, _tag, warnings = evaluate_results(
    config,
    collect_results(results_dir),
    version,
    candidate_sha,
  )
  if outcome != "PASS":
    raise PreMergeGateError(
      f"integration blocked: required test logs are {outcome}: "
      + "; ".join(warnings)
    )


def accept_pre_merge_candidate(
  root: Path,
  *,
  candidate_sha: str,
  recorded_parent_tip: str,
  read_authoritative_parent_tip: Callable[[], str],
  accept_if_parent: Callable[[str, str], bool],
  results_dir: Path,
  config: dict,
  version: str,
  canonical_log: Path,
  required_platforms: tuple[str, ...],
  verify_hosted: Callable[[dict], bool] | None = None,
  provider_repo: str | None = None,
) -> None:
  """Validate and atomically accept a candidate against one destination tip.\n\n  accept_if_parent is the hard mutation boundary.  It must perform one\n  compare-and-swap operation that changes the authoritative destination only\n  when its current tip still equals recorded_parent_tip.  Returning False\n  means the lease was lost and no destination mutation occurred.\n  """
  authoritative_parent_tip = read_authoritative_parent_tip()
  check_pre_merge_candidate(
    root,
    candidate_sha=candidate_sha,
    recorded_parent_tip=recorded_parent_tip,
    authoritative_parent_tip=authoritative_parent_tip,
    results_dir=results_dir,
    config=config,
    version=version,
    canonical_log=canonical_log,
    required_platforms=required_platforms,
    verify_hosted=verify_hosted,
    provider_repo=provider_repo,
  )
  if not accept_if_parent(candidate_sha, recorded_parent_tip):
    raise PreMergeGateError(
      "integration blocked: destination tip advanced before acceptance"
    )
