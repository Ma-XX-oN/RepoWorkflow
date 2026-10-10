#!/usr/bin/env python3
"""Live GitHub acceptance probe for issue #97 (sandbox only).

Run with a separately authorized sandbox repository and trusted verifier.
This probe creates a temporary draft PR, updates a sandbox issue, and leaves
immutable reservation refs as audit evidence.  It NEVER merges or publishes
a success check.  Do not run against a production issue or main destination.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters" / "repo-host-github.py"


def gh(repository: str, path: str) -> dict:
  result = subprocess.run(
    ["gh", "api", f"repos/{repository}/{path}"],
    text=True, capture_output=True, check=False, timeout=30,
  )
  if result.returncode:
    raise RuntimeError("GitHub sandbox prerequisite read failed")
  value = json.loads(result.stdout)
  if not isinstance(value, dict):
    raise RuntimeError("expected GitHub JSON object")
  return value


def invoke(repository: str, operation: str, identity: str,
           parameters: dict, permitted: bool = True) -> dict:
  request = {
    "schema_version": 1, "operation": operation,
    "repository": repository, "request_id": identity,
    "parameters": parameters,
  }
  result = subprocess.run(
    [sys.executable, str(ADAPTER)],
    input=json.dumps(request), text=True, capture_output=True,
    check=False, timeout=90,
  )
  if permitted:
    if result.returncode or result.stderr:
      raise RuntimeError(
        f"{operation} failed: {result.stderr[:1000]}"
      )
    value = json.loads(result.stdout)
    if value["operation"] != operation or value["request_id"] != identity:
      raise RuntimeError("adapter identity mismatch")
    if value["status"] not in {"applied", "unchanged"}:
      raise RuntimeError("adapter did not prove mutation result")
    return value
  if result.returncode == 0 or result.stdout:
    raise RuntimeError(operation + " unexpectedly succeeded")
  value = json.loads(result.stderr)
  if value["error"] not in {"conflict", "unauthorized", "unsupported"}:
    raise RuntimeError("unexpected refusal reason: " + value["error"])
  return value


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--repository", required=True)
  parser.add_argument("--sandbox-issue", type=int, required=True)
  parser.add_argument("--source-ref", required=True)
  parser.add_argument("--target-ref", required=True)
  parser.add_argument("--run-id", required=True)
  args = parser.parse_args()
  if args.sandbox_issue <= 0:
    parser.error("--sandbox-issue must be positive")
  if not args.source_ref.startswith("refs/heads/") or not (
    args.target_ref.startswith("refs/heads/")
  ):
    parser.error("explicit branch refs are required")
  if args.source_ref == args.target_ref:
    parser.error("sandbox source and destination must differ")
  capabilities = invoke(args.repository, "capabilities",
                        args.run_id + "-cap", {})
  available = capabilities["result"]["operations"]
  for operation in (
    "issue.update", "issue.comment",
    "pull_request.create", "pull_request.update",
  ):
    if available[operation] is not True:
      raise RuntimeError("required provider capability unavailable: "
                         + operation)
  issue = gh(args.repository, "issues/" + str(args.sandbox_issue))
  if "pull_request" in issue or issue["state"] != "open":
    raise RuntimeError("sandbox issue must be an open issue, not PR")
  original_title = issue["title"]
  source = gh(args.repository, "git/ref/heads/"
              + args.source_ref.removeprefix("refs/heads/"))
  head_sha = source["object"]["sha"]
  run = args.run_id
  changed_title = "RWF #97 live probe " + run
  created_pr = None
  try:
    changed = invoke(args.repository, "issue.update", run + "-issue",
                     {"number": args.sandbox_issue,
                      "title": changed_title})
    repeated = invoke(args.repository, "issue.update", run + "-issue",
                      {"number": args.sandbox_issue,
                       "title": changed_title})
    if changed["result"]["title"] != changed_title or (
      repeated["status"] != "unchanged"
    ):
      raise RuntimeError("issue idempotency contract violated")
    params = {"number": args.sandbox_issue, "body": "RWF probe " + run}
    comment = invoke(args.repository, "issue.comment",
                     run + "-comment", params)
    replay = invoke(args.repository, "issue.comment",
                    run + "-comment", params)
    if comment["result"]["comment_id"] != replay["result"]["comment_id"]:
      raise RuntimeError("comment duplicate or identity changed")
    pr_data = {
      "source_ref": args.source_ref, "target_ref": args.target_ref,
      "expected_source_sha": head_sha, "title": "RWF live probe " + run,
      "body": "Temporary sandbox draft; no merge authorized.", "draft": True,
    }
    created = invoke(args.repository, "pull_request.create",
                     run + "-create", pr_data)
    created_pr = created["result"]["number"]
    same = invoke(args.repository, "pull_request.create",
                  run + "-create", pr_data)
    if same["result"]["number"] != created_pr:
      raise RuntimeError("PR creation replay duplicated provider state")
    edit = {
      "number": created_pr, "expected_head_sha": head_sha,
      "title": "RWF live probe updated " + run,
    }
    invoke(args.repository, "pull_request.update", run + "-update", edit)
    again = invoke(args.repository, "pull_request.update",
                   run + "-update", edit)
    if again["status"] != "unchanged":
      raise RuntimeError("PR update replay is not idempotent")
    stale = {**edit, "expected_head_sha": "0" * 40}
    refused = invoke(args.repository, "pull_request.update",
                     run + "-stale", stale, permitted=False)
    if refused["error"] != "conflict":
      raise RuntimeError("stale PR head did not conflict")
    target = gh(args.repository, "git/ref/heads/"
                + args.target_ref.removeprefix("refs/heads/"))
    refused_params = {
      "pull_request.merge": {
        "number": created_pr, "tested_head_sha": head_sha,
        "expected_destination_sha": target["object"]["sha"],
        "eligibility_ref": "unverified-probe",
        "authorization_ref": "unverified-probe",
      },
      "check.publish": {
        "candidate_sha": head_sha, "context": "rwf/probe",
        "verification_ref": "unverified-probe", "conclusion": "success",
      },
    }
    for op, params in refused_params.items():
      refused = invoke(args.repository, op, run + "-" + op,
                       params, permitted=False)
      if refused["error"] != "unsupported":
        raise RuntimeError(op + " did not fail closed")
    print(json.dumps({
      "result": "PASS", "repository": args.repository,
      "issue": args.sandbox_issue, "pr": created_pr,
      "source_sha": head_sha,
      "run_id": run, "no_merge": True,
    }, sort_keys=True))
    return 0
  finally:
    # Clean up only the issue title and temporary PR.  Preserve the test
    # comment and immutable idempotency audit reservations deliberately.
    if created_pr is not None:
      subprocess.run(
        ["gh", "api", "--method", "PATCH",
         f"repos/{args.repository}/pulls/{created_pr}",
         "-f", "state=closed"],
        capture_output=True, text=True, check=False, timeout=30,
      )
    if original_title != changed_title:
      try:
        invoke(args.repository, "issue.update", run + "-restore",
               {"number": args.sandbox_issue, "title": original_title})
      except Exception:
        print("sandbox issue title requires manual restoration",
              file=sys.stderr)


if __name__ == "__main__":
  raise SystemExit(main())
