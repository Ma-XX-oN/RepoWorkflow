#!/usr/bin/env python3
"""Read-only, non-secret GitHub Actions configuration discovery for #97.

A denied API response is evidence of this token's inspection limits,
not evidence that the requested protected resource does not exist.
Never write provider settings or print credentials.
"""
from __future__ import annotations

import json
import os
import subprocess


ROUTES = {
  "sandbox_environment":
    "repos/Ma-XX-oN/RepoWorkflow/environments/rwf97-sandbox",
  "deployment_branches":
    "repos/Ma-XX-oN/RepoWorkflow/environments/"
    "rwf97-sandbox/deployment-branch-policies",
  "repository_actions_permissions":
    "repos/Ma-XX-oN/RepoWorkflow/actions/permissions",
  "workflow_token_policy":
    "repos/Ma-XX-oN/RepoWorkflow/actions/permissions/workflow",
  "trusted_runners":
    "repos/Ma-XX-oN/RepoWorkflow/actions/runners",
  "repository_variables":
    "repos/Ma-XX-oN/RepoWorkflow/actions/variables",
  "registered_workflows":
    "repos/Ma-XX-oN/RepoWorkflow/actions/workflows",
}


def inspection_status(returncode: int, stderr: str) -> str:
  if returncode == 0:
    return "READABLE"
  message = stderr.lower()
  if "http 401" in message:
    return "AUTHENTICATION_DENIED"
  if "http 403" in message:
    return "INSUFFICIENT_INSPECTION_PERMISSION"
  if "http 404" in message:
    return "NOT_FOUND_OR_CONCEALED"
  if "http 429" in message:
    return "RATE_LIMITED"
  return "UNKNOWN_INSPECTION_FAILURE"


def main() -> int:
  observations = {}
  for key, route in ROUTES.items():
    response = subprocess.run(
      ["gh", "api", "--method", "GET", route],
      capture_output=True, text=True, timeout=30, check=False,
    )
    status = inspection_status(response.returncode, response.stderr)
    observations[key] = {"status": status}
    if status == "READABLE":
      try:
        payload = json.loads(response.stdout)
      except ValueError:
        observations[key]["status"] = "INVALID_PROVIDER_RESPONSE"
        continue
      if key == "sandbox_environment" and isinstance(payload, dict):
        observations[key]["name_matches"] = (
          payload.get("name") == "rwf97-sandbox"
        )
        observations[key]["has_protection_rules"] = bool(
          payload.get("protection_rules")
        )
      if key == "deployment_branches" and isinstance(payload, dict):
        observations[key]["total_count"] = payload.get("total_count")
      if key == "workflow_token_policy" and isinstance(payload, dict):
        observations[key]["default_workflow_permissions"] = payload.get(
          "default_workflow_permissions"
        )
        observations[key]["can_approve_pull_request_reviews"] = payload.get(
          "can_approve_pull_request_reviews"
        )
      if key == "registered_workflows" and isinstance(payload, dict):
        items = payload.get("workflows", [])
        if isinstance(items, list):
          observations[key]["issue97_live_registered"] = any(
            item.get("path") ==
            ".github/workflows/issue-97-live-mutation.yml"
            for item in items if isinstance(item, dict)
          )
  print(json.dumps({
    "result": "INSPECTION_ONLY",
    "actor": os.environ.get("GITHUB_ACTOR", "unavailable"),
    "repository": "Ma-XX-oN/RepoWorkflow",
    "observations": observations,
    "provider_mutations": 0,
    "secrets_disclosed": False,
  }, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
