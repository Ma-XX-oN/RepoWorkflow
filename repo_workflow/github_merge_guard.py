"""Guard a GitHub PR merge with verified server protection and exact identity.

GitHub, not client-side polling, must serialize and enforce current-base merge
requirements. This module refuses merge when protection cannot be authenticated.
"""
from __future__ import annotations

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
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
  required_check_name: str = "repo-workflow/exact-candidate",
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
    or not isinstance(required_check_name, str)
    or not required_check_name.strip()
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
    configured_checks = set(checks.get("contexts") or ()) if isinstance(checks, dict) else set()
    if isinstance(checks, dict):
      configured_checks.update(
        item.get("context") for item in (checks.get("checks") or [])
        if isinstance(item, dict)
      )
    if (
      branch.get("protected") is not True
      or branch.get("commit", {}).get("sha") != recorded_parent_tip
      or not isinstance(checks, dict) or checks.get("strict") is not True
      or required_check_name not in configured_checks
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
  except (AttributeError, KeyError, TypeError, ValueError, OSError) as error:
    raise PreMergeGateError(
      "integration blocked: GitHub protection/merge unavailable"
    ) from error


def _github_request(url: str, payload: dict | None = None) -> dict:
  """Authenticated GitHub API request; never retry an ambiguous merge POST."""
  if not url.startswith("https://api.github.com/repos/"):
    raise ValueError("unexpected GitHub endpoint")
  token = os.environ.get("GITHUB_TOKEN")
  if not token:
    raise ValueError("missing GitHub credential")
  headers = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "Authorization": "Bearer " + token,
    "User-Agent": "RepoWorkflow-merge-guard",
  }
  data = None if payload is None else json.dumps(payload).encode("utf-8")
  if data is not None:
    headers["Content-Type"] = "application/json"
  request = Request(url, data=data, headers=headers,
                    method="GET" if data is None else "PUT")
  try:
    with urlopen(request, timeout=15) as response:
      result = json.load(response)
  except (HTTPError, URLError, TimeoutError, ValueError) as error:
    raise PreMergeGateError(
      "integration blocked: GitHub provider request failed"
    ) from error
  if not isinstance(result, dict):
    raise PreMergeGateError("integration blocked: invalid GitHub response")
  return result


def merge_github_pr(
  *, repo: str, pr_number: int, candidate_sha: str,
  recorded_parent_tip: str, evidence_gate: Callable[[], None],
  required_check_name: str = "repo-workflow/exact-candidate",
) -> str:
  """Production adapter; GitHub protections must be enabled first."""
  return merge_protected_pr(
    repo=repo, pr_number=pr_number, candidate_sha=candidate_sha,
    recorded_parent_tip=recorded_parent_tip,
    read=lambda url: _github_request(url),
    merge=lambda url, body: _github_request(url, body),
    evidence_gate=evidence_gate, required_check_name=required_check_name,
  )
