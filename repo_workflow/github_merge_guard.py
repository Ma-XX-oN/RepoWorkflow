"""Guard a GitHub PR merge with verified server protection and exact identity.

GitHub, not client-side polling, must serialize and enforce current-base merge
requirements. This module refuses merge when protection cannot be authenticated.
"""
from __future__ import annotations

import re
from typing import Callable

from .pre_merge_gate import PreMergeGateError


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


def merge_protected_pr(
  *,
  repo: str,
  pr_number: int,
  candidate_sha: str,
  recorded_parent_tip: str,
  read: Callable[[str], dict],
  merge: Callable[[str, dict], dict],
  evidence_gate: Callable[[], None],
) -> str:
  """Validate provider state and delegate the atomic decision to GitHub.

  The evidence gate must check the exact tested candidate. The server must
  require strict current-base status checks and prevent administrator bypass.
  The provider merge endpoint must use the expected PR head SHA.
  """
  if (
    not isinstance(repo, str) or not _REPO.fullmatch(repo)
    or type(pr_number) is not int or pr_number < 1
    or not isinstance(candidate_sha, str) or not _SHA.fullmatch(candidate_sha)
    or not isinstance(recorded_parent_tip, str)
    or not _SHA.fullmatch(recorded_parent_tip)
  ):
    raise PreMergeGateError("integration blocked: invalid GitHub identity")
  base = "https://api.github.com/repos/" + repo
  try:
    pr = read(base + "/pulls/" + str(pr_number))
    if not isinstance(pr, dict):
      raise ValueError("invalid pull request")
    target = pr["base"]["ref"]
    base_sha = pr["base"]["sha"]
    head_sha = pr["head"]["sha"]
    if (
      target != "main"
      or base_sha != recorded_parent_tip
      or head_sha != candidate_sha
      or pr.get("state") != "open"
      or pr.get("draft") is not False
    ):
      raise PreMergeGateError("integration blocked: candidate or base changed")
    branch = read(base + "/branches/main")
    protection = read(base + "/branches/main/protection")
    if not isinstance(branch, dict) or not isinstance(protection, dict):
      raise ValueError("invalid branch protection")
    checks = protection.get("required_status_checks")
    administrators = protection.get("enforce_admins")
    if (
      branch.get("protected") is not True
      or branch.get("commit", {}).get("sha") != recorded_parent_tip
      or not isinstance(checks, dict) or checks.get("strict") is not True
      or not (checks.get("contexts") or checks.get("checks"))
      or not isinstance(administrators, dict)
      or administrators.get("enabled") is not True
      or not isinstance(protection.get("required_pull_request_reviews"), dict)
      or protection.get("allow_force_pushes", {}).get("enabled") is not False
      or protection.get("allow_deletions", {}).get("enabled") is not False
    ):
      raise PreMergeGateError("integration blocked: server protection incomplete")
    evidence_gate()
    result = merge(
      base + "/pulls/" + str(pr_number) + "/merge",
      {"sha": candidate_sha, "merge_method": "merge"},
    )
    if not isinstance(result, dict) or result.get("merged") is not True:
      raise PreMergeGateError("integration blocked: server rejected merge")
    merged_sha = result.get("sha")
    if not isinstance(merged_sha, str) or not _SHA.fullmatch(merged_sha):
      raise PreMergeGateError("integration blocked: invalid merge response")
    return merged_sha
  except PreMergeGateError:
    raise
  except (KeyError, TypeError, ValueError, OSError) as error:
    raise PreMergeGateError(
      "integration blocked: GitHub protection/merge unavailable"
    ) from error
