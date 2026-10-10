#!/usr/bin/env python3
"""Live GitHub acceptance probe for issue #97 (sandbox only).

Run with a separately authorized sandbox repository and trusted verifier.
This probe creates a temporary draft PR, updates a sandbox issue, and leaves
immutable reservation refs as audit evidence.  It NEVER merges or publishes
a success check.  Do not run against a production issue or main destination.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from threading import Barrier
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters" / "repo-host-github.py"


def gh(repository: str, path: str) -> dict:
  result = subprocess.run(
    ["gh", "api", f"repos/{repository}/{path}".rstrip("/")],
    text=True, capture_output=True, check=False, timeout=30,
  )
  if result.returncode:
    raise RuntimeError("GitHub sandbox prerequisite read failed")
  value = json.loads(result.stdout)
  if not isinstance(value, (dict, list)):
    raise RuntimeError("expected GitHub JSON object or array")
  return value


def verify_reservation(repository: str, operation: str,
                       request_id: str, parameters: dict) -> None:
  """Independently verify GitHub's persisted request digest and tag."""
  identity = chr(0).join((repository, operation, request_id))
  ref_name = "rwf-host-request-" + hashlib.sha256(
    identity.encode("utf-8")
  ).hexdigest()
  expected = {
    "schema_version": 1, "operation": operation,
    "repository": repository, "request_id": request_id,
    "parameters": parameters,
  }
  digest = hashlib.sha256(json.dumps(
    expected, sort_keys=True, separators=(",", ":")
  ).encode("utf-8")).hexdigest()
  observed_ref = gh(repository, "git/ref/tags/" + ref_name)
  if observed_ref.get("ref") != "refs/tags/" + ref_name:
    raise RuntimeError("remote reservation reference mismatch")
  item = observed_ref.get("object")
  if not isinstance(item, dict) or not isinstance(item.get("sha"), str):
    raise RuntimeError("remote reservation commit missing")
  commit = gh(repository, "git/commits/" + item["sha"])
  if commit.get("message") != "RWF-HOST-RESERVATION-V1 " + digest:
    raise RuntimeError("remote reservation request digest mismatch")


def verify_remote_comment(repository: str, number: int,
                          request_id: str, comment_id: str,
                          body: str) -> None:
  identity = repository + "\0issue.comment\0" + request_id
  marker = "<!-- RWF-HOST-REQUEST-V1:" + hashlib.sha256(
    identity.encode("utf-8")
  ).hexdigest() + " -->"
  matches = []
  for page in range(1, 1002):
    items = gh(repository, f"issues/{number}/comments?"
               f"per_page=100&page={page}")
    if not isinstance(items, list):
      raise RuntimeError("invalid remote comments page")
    matches.extend(item for item in items if isinstance(item, dict)
                   and marker in str(item.get("body", "")))
    if len(items) < 100:
      break
  else:
    raise RuntimeError("remote comment scan exceeded bound")
  if len(matches) != 1 or str(matches[0].get("id")) != comment_id:
    raise RuntimeError("provider persisted duplicate or wrong comment")
  if matches[0].get("body") != body + "\n" + marker:
    raise RuntimeError("provider persisted incorrect comment content")


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


def verify_concurrent_comment(repository: str, number: int,
                              run: str) -> None:
  """Race independent Python processes and reconcile exactly one comment."""
  identity = run + "-race-comment"
  params = {"number": number, "body": "RWF concurrent probe " + run}
  request = {
    "schema_version": 1, "operation": "issue.comment",
    "repository": repository, "request_id": identity,
    "parameters": params,
  }
  gate = Barrier(2)

  def execute(_):
    gate.wait(timeout=20)
    proc = subprocess.run(
      [sys.executable, str(ADAPTER)],
      input=json.dumps(request), text=True, capture_output=True,
      check=False, timeout=90,
    )
    if proc.returncode == 0 and not proc.stderr:
      value = json.loads(proc.stdout)
      if value.get("request_id") != identity or (
        value.get("status") not in {"applied", "unchanged"}
      ):
        raise RuntimeError("concurrent provider result identity mismatch")
      return value["status"]
    if proc.returncode != 0 and not proc.stdout:
      error = json.loads(proc.stderr)
      if error.get("error") == "unknown_outcome" and (
        error.get("request_id") == identity
      ):
        return "unknown_outcome"
    raise RuntimeError("concurrent provider mutation failed unexpectedly")

  with ThreadPoolExecutor(max_workers=2) as pool:
    outcomes = list(pool.map(execute, (0, 1)))
  if not set(outcomes) <= {"applied", "unchanged", "unknown_outcome"}:
    raise RuntimeError("invalid concurrent mutation outcome")
  observed = invoke(repository, "issue.comment", identity, params)
  if observed["status"] != "unchanged":
    raise RuntimeError("concurrent replay was not reconciled")
  verify_remote_comment(repository, number, identity,
                        observed["result"]["comment_id"], params["body"])
  verify_reservation(repository, "issue.comment", identity, params)


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
  if args.repository.lower() == "ma-xx-on/repoworkflow":
    parser.error("production RepoWorkflow repository is not a sandbox")
  prefix = "refs/heads/rwf97-sandbox-"
  if not args.source_ref.startswith(prefix) or not (
    args.target_ref.startswith(prefix)
  ):
    parser.error("dedicated rwf97-sandbox- branch refs are required")
  metadata = gh(args.repository, "")
  default = metadata.get("default_branch")
  if args.source_ref == "refs/heads/" + str(default) or (
    args.target_ref == "refs/heads/" + str(default)
  ):
    parser.error("default branch must never be used as a fixture")
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
  if not issue.get("title", "").startswith("RWF #97 SANDBOX "):
    raise RuntimeError("sandbox issue lacks exact dedicated test title")
  original_title = issue["title"]
  source = gh(args.repository, "git/ref/heads/"
              + args.source_ref.removeprefix("refs/heads/"))
  head_sha = source["object"]["sha"]
  target_preflight = gh(
    args.repository, "git/ref/heads/"
    + args.target_ref.removeprefix("refs/heads/")
  )
  if target_preflight["object"]["sha"] == head_sha:
    raise RuntimeError("sandbox branches must have different commits")
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
    if gh(args.repository, "issues/" + str(args.sandbox_issue))[
      "title"
    ] != changed_title:
      raise RuntimeError("provider did not persist issue title")
    verify_reservation(args.repository, "issue.update",
                       run + "-issue",
                       {"number": args.sandbox_issue, "title": changed_title})
    params = {"number": args.sandbox_issue, "body": "RWF probe " + run}
    comment = invoke(args.repository, "issue.comment",
                     run + "-comment", params)
    replay = invoke(args.repository, "issue.comment",
                    run + "-comment", params)
    if comment["result"]["comment_id"] != replay["result"]["comment_id"]:
      raise RuntimeError("comment duplicate or identity changed")
    changed_comment = {**params, "body": "Changed RWF probe " + run}
    refused = invoke(args.repository, "issue.comment",
                     run + "-comment", changed_comment, permitted=False)
    if refused["error"] != "conflict":
      raise RuntimeError("same request ID accepted changed comment body")
    verify_remote_comment(args.repository, args.sandbox_issue,
                          run + "-comment", comment["result"]["comment_id"],
                          params["body"])
    verify_reservation(args.repository, "issue.comment",
                       run + "-comment", params)
    verify_concurrent_comment(args.repository, args.sandbox_issue, run)
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
    observed_pr = gh(args.repository, "pulls/" + str(created_pr))
    if observed_pr["head"]["sha"] != head_sha or (
      observed_pr["head"]["ref"] != args.source_ref.removeprefix("refs/heads/")
    ) or observed_pr["base"]["ref"] != args.target_ref.removeprefix(
      "refs/heads/"
    ) or observed_pr["draft"] is not True:
      raise RuntimeError("provider PR creation identity mismatch")
    verify_reservation(args.repository, "pull_request.create",
                       run + "-create", pr_data)
    edit = {
      "number": created_pr, "expected_head_sha": head_sha,
      "title": "RWF live probe updated " + run,
    }
    invoke(args.repository, "pull_request.update", run + "-update", edit)
    again = invoke(args.repository, "pull_request.update",
                   run + "-update", edit)
    if again["status"] != "unchanged":
      raise RuntimeError("PR update replay is not idempotent")
    if gh(args.repository, "pulls/" + str(created_pr))[
      "title"
    ] != edit["title"]:
      raise RuntimeError("provider did not persist PR update")
    verify_reservation(args.repository, "pull_request.update",
                       run + "-update", edit)
    stale = {**edit, "expected_head_sha": "0" * 40}
    refused = invoke(args.repository, "pull_request.update",
                     run + "-stale", stale, permitted=False)
    if refused["error"] not in {"conflict", "unauthorized"}:
      raise RuntimeError("stale PR head was not rejected")
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
  finally:
    # Preserve the immutable reservations and audit comment.  A failed
    # cleanup is a failed probe, never a silent PASS.
    errors = []
    if created_pr is not None:
      try:
        closing = {"number": created_pr,
                   "expected_head_sha": head_sha, "state": "closed"}
        invoke(args.repository, "pull_request.update",
               run + "-close", closing)
        if gh(args.repository, "pulls/" + str(created_pr))[
          "state"
        ] != "closed":
          errors.append("temporary PR close failed")
        else:
          verify_reservation(args.repository, "pull_request.update",
                             run + "-close", closing)
      except Exception:
        errors.append("temporary PR close failed")
    if original_title != changed_title:
      try:
        invoke(args.repository, "issue.update", run + "-restore",
               {"number": args.sandbox_issue, "title": original_title})
        if gh(args.repository, "issues/" + str(args.sandbox_issue))[
          "title"
        ] != original_title:
          errors.append("sandbox issue title not restored")
        else:
          verify_reservation(args.repository, "issue.update",
                             run + "-restore", {
            "number": args.sandbox_issue, "title": original_title,
          })
      except Exception:
        errors.append("sandbox issue title requires manual restoration")
    if errors:
      raise RuntimeError("; ".join(errors))
  print(json.dumps({
    "result": "PASS", "repository": args.repository,
    "issue": args.sandbox_issue, "pr": created_pr,
    "source_sha": head_sha, "run_id": run,
    "no_merge": True, "cleanup_verified": True,
  }, sort_keys=True))
  return 0

if __name__ == "__main__":
  raise SystemExit(main())
