#!/usr/bin/env python3
"""Authenticated REAL private-sandbox denial audit via shipped Python CLI.

Read-only GitHub token; no #80 verifier. Every mutation must fail first.
Authoritative before/after GitHub reads must match exactly.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters/repo-host-github.py"
REPOSITORY = "Ma-XX-oN/Disposable-000"
ISSUE = 1
PR = 2


def api(path: str) -> object:
  result = subprocess.run(
    ["gh", "api", "--method", "GET",
     "repos/" + REPOSITORY + "/" + path],
    text=True, capture_output=True, timeout=30, check=False,
  )
  if result.returncode:
    raise RuntimeError("cannot inspect real sandbox provider state")
  return json.loads(result.stdout)


def snapshot() -> dict:
  issue = api("issues/" + str(ISSUE))
  pr = api("pulls/" + str(PR))
  source = api("git/ref/heads/rwf97-sandbox-source")
  target = api("git/ref/heads/rwf97-sandbox-target")
  comments = api("issues/" + str(ISSUE) + "/comments?per_page=100")
  if not isinstance(comments, list) or len(comments) >= 100:
    raise RuntimeError("fixture comment snapshot incomplete")
  refs = api("git/matching-refs/tags/rwf-host-request-")
  if not isinstance(refs, list):
    raise RuntimeError("fixture tag snapshot invalid")
  return {
    "issue_title": issue["title"],
    "issue_state": issue["state"],
    "issue_comments": [(x["id"], x["body"]) for x in comments],
    "pr_title": pr["title"], "pr_state": pr["state"],
    "pr_base": pr["base"]["ref"], "pr_head": pr["head"]["sha"],
    "pr_draft": pr["draft"],
    "source_sha": source["object"]["sha"],
    "target_sha": target["object"]["sha"],
    "reservation_refs": sorted(x["ref"] for x in refs),
  }


def deny(operation: str, request_id: str, params: dict) -> str:
  request = {
    "schema_version": 1,
    "operation": operation, "repository": REPOSITORY,
    "request_id": request_id, "parameters": params,
  }
  process = subprocess.run(
    [sys.executable, str(ADAPTER)],
    input=json.dumps(request), capture_output=True, text=True,
    check=False, timeout=45,
  )
  if process.returncode == 0 or process.stdout:
    raise RuntimeError("unauthorized real mutation succeeded: "
                       + operation)
  outcome = json.loads(process.stderr)
  if outcome["request_id"] != request_id:
    raise RuntimeError("provider denial identity mismatch")
  if outcome["error"] not in {"unauthorized", "unsupported"}:
    raise RuntimeError("unexpected refusal semantics: "
                       + outcome["error"])
  return outcome["error"]


def main() -> int:
  if os.environ.get("RWF_REPO_HOST_AUTH_COMMAND"):
    raise RuntimeError("negative provider probe cannot use a verifier")
  if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
    raise RuntimeError("not executing in isolated sandbox")
  before = snapshot()
  if before["issue_title"] != "RWF #97 SANDBOX live-mutation fixture":
    raise RuntimeError("dedicated issue fixture changed")
  if before["pr_state"] != "closed" or before["pr_base"] != (
    "rwf97-sandbox-target"
  ):
    raise RuntimeError("dedicated closed PR fixture changed")
  identifier = "rwf97-private-denial-" + os.environ.get(
    "GITHUB_RUN_ID", "local"
  )
  calls = [
    ("issue.update", "issue", {
      "number": ISSUE,
      "title": "NEVER AUTHORIZE WITHOUT TRUSTED #80 GRANT",
    }),
    ("issue.comment", "comment", {
      "number": ISSUE, "body": "MUST NOT BE PUBLISHED",
    }),
    ("pull_request.create", "create", {
      "source_ref": "refs/heads/rwf97-sandbox-source",
      "target_ref": "refs/heads/rwf97-sandbox-target",
      "expected_source_sha": before["source_sha"],
      "title": "UNAUTHORIZED PR", "body": "never published",
      "draft": True,
    }),
    ("pull_request.update", "update", {
      "number": PR, "expected_head_sha": before["source_sha"],
      "title": "UNAUTHORIZED PR UPDATE",
    }),
    ("pull_request.merge", "merge", {
      "number": PR, "tested_head_sha": before["source_sha"],
      "expected_destination_sha": before["target_sha"],
      "eligibility_ref": "untrusted", "authorization_ref": "untrusted",
    }),
    ("check.publish", "check", {
      "candidate_sha": before["source_sha"], "context": "rwf/deny",
      "verification_ref": "untrusted", "conclusion": "success",
    }),
  ]
  results = {}
  for operation, suffix, params in calls:
    results[operation] = deny(operation, identifier + "-" + suffix, params)
  after = snapshot()
  if before != after:
    raise RuntimeError("unauthorized attempt altered real GitHub state")
  print(json.dumps({
    "result": "PASS",
    "repository": REPOSITORY,
    "provider_state_unchanged": True,
    "denials": results,
    "attempted_operations": len(calls),
    "adapter": "shipped Python CLI",
  }, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
