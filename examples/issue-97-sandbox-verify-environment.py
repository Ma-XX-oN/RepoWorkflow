#!/usr/bin/env python3
"""Trusted sandbox-side environment guard for issue #97.

Deploy ONLY from the disposable sandbox repository's protected main branch.
The code and its authorization dependencies must be independently reviewed.
"""
from __future__ import annotations

import json
import os
import subprocess


def github_get(route: str) -> dict:
  result = subprocess.run(
    ["gh", "api", "--method", "GET", route],
    capture_output=True, text=True, check=False, timeout=30,
  )
  if result.returncode:
    raise RuntimeError("cannot verify GitHub environment policy")
  value = json.loads(result.stdout)
  if not isinstance(value, dict):
    raise RuntimeError("invalid GitHub environment data")
  return value


def check_policy(environment: dict, branch_policies: dict,
                 repository: str, branch: str) -> None:
  if repository.lower() == "ma-xx-on/repoworkflow":
    raise RuntimeError("production repository forbidden")
  if environment.get("name") != "rwf97-acceptance":
    raise RuntimeError("wrong protected environment")
  reviews = environment.get("protection_rules")
  if not isinstance(reviews, list):
    raise RuntimeError("missing environment rules")
  if not any(
    rule.get("type") == "required_reviewers"
    and rule.get("prevent_self_review") is True
    and isinstance(rule.get("reviewers"), list)
    and len(rule["reviewers"]) > 0
    for rule in reviews if isinstance(rule, dict)
  ):
    raise RuntimeError("independent deployment approval not enforced")
  policy = environment.get("deployment_branch_policy")
  if not isinstance(policy, dict) or (
    policy.get("custom_branch_policies") is not True
  ):
    raise RuntimeError("exact deployment branch restriction absent")
  found = branch_policies.get("branch_policies")
  if type(branch_policies.get("total_count")) is not int or (
    branch_policies["total_count"] != 1
  ) or not isinstance(found, list) or len(found) != 1 or (
    found[0].get("name") != branch
  ):
    raise RuntimeError("untrusted branch deployment policy")
  if branch != "main":
    raise RuntimeError("sandbox workflow must run on protected main")


def main() -> int:
  repo = os.environ["GITHUB_REPOSITORY"]
  branch = os.environ["GITHUB_REF"]
  if branch != "refs/heads/main":
    raise RuntimeError("invalid workflow source ref")
  prefix = f"repos/{repo}/environments/rwf97-acceptance"
  environment = github_get(prefix)
  branches = github_get(prefix + "/deployment-branch-policies")
  check_policy(environment, branches, repo, "main")
  print(json.dumps({
    "result": "PASS", "environment": "rwf97-acceptance",
    "workflow_repository": repo, "protected_branch": "main",
    "independent_review": True, "mutations": 0,
  }, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
