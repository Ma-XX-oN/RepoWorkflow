#!/usr/bin/env python3
"""Fail closed unless #97's privileged sandbox environment is reviewed."""
from __future__ import annotations

import json
import subprocess


def validate_environment(value: dict) -> None:
  if not isinstance(value, dict) or value.get("name") != "rwf97-sandbox":
    raise RuntimeError("sandbox environment identity mismatch")
  rules = value.get("protection_rules")
  if not isinstance(rules, list):
    raise RuntimeError("sandbox protection rules missing")
  approved = any(
    isinstance(rule, dict) and rule.get("type") == "required_reviewers"
    and rule.get("prevent_self_review") is True
    and isinstance(rule.get("reviewers"), list)
    and len(rule["reviewers"]) > 0
    for rule in rules
  )
  if not approved:
    raise RuntimeError("independent required reviewers not configured")
  branches = value.get("deployment_branch_policy")
  if not isinstance(branches, dict) or not (
    branches.get("custom_branch_policies") is True
  ):
    raise RuntimeError("protected custom deployment branch policy required")


def main() -> int:
  result = subprocess.run(
    ["gh", "api",
     "repos/Ma-XX-oN/RepoWorkflow/environments/rwf97-sandbox"],
    capture_output=True, text=True, check=False, timeout=30,
  )
  if result.returncode:
    raise RuntimeError("cannot verify sandbox environment protections")
  validate_environment(json.loads(result.stdout))
  print(json.dumps({"result": "PASS",
                    "environment": "rwf97-sandbox",
                    "independent_review": True,
                    "branch_policy": True}, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
