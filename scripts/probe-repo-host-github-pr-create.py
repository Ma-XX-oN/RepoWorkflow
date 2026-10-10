#!/usr/bin/env python3
"""#81 live GitHub pull_request.create acceptance, disposable repo ONLY.

Runs actual shipped Python adapter, independently verifies persisted
GitHub PR and reservation identity, and closes the disposable PR
through the sandbox's own fixture-cleanup GitHub API permission.
It NEVER merges and never targets production or sandbox main.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters/repo-host-github.py"
REPO = "Ma-XX-oN/Disposable-000"
SOURCE = "refs/heads/rwf97-sandbox-source"
TARGET = "refs/heads/rwf97-sandbox-target"
SHA = "9bf44e1aaac2e49fe26949df3369c4fc10b462fc"


def github(route: str) -> object:
  response = subprocess.run(
    ["gh", "api", "--method", "GET", f"repos/{REPO}/{route}"],
    text=True, capture_output=True, check=False, timeout=30,
  )
  if response.returncode:
    raise RuntimeError("authoritative provider read unavailable")
  return json.loads(response.stdout)


def invoke(request: dict) -> tuple[int, dict]:
  result = subprocess.run(
    [sys.executable, str(ADAPTER)], input=json.dumps(request),
    text=True, capture_output=True, check=False, timeout=90,
  )
  if result.returncode == 0:
    if result.stderr:
      raise RuntimeError("unexpected success stderr")
    return 0, json.loads(result.stdout)
  if result.stdout:
    raise RuntimeError("failure emitted success response")
  return result.returncode, json.loads(result.stderr)


def identity(operation: str, request_id: str) -> str:
  return hashlib.sha256(
    "\0".join((REPO, operation, request_id)).encode("utf-8")
  ).hexdigest()


def digest(request: dict) -> str:
  return hashlib.sha256(json.dumps(
    request, sort_keys=True, separators=(",", ":")
  ).encode("utf-8")).hexdigest()


def assert_reservation(request: dict) -> None:
  tag = "rwf-host-request-" + identity(
    request["operation"], request["request_id"]
  )
  tag_data = github("git/ref/tags/" + tag)
  if tag_data["ref"] != "refs/tags/" + tag:
    raise RuntimeError("wrong reservation ref")
  record = github("git/commits/" + tag_data["object"]["sha"])
  if record["message"] != "RWF-HOST-RESERVATION-V1 " + digest(request):
    raise RuntimeError("reservation request digest differs")


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--run-id", required=True)
  args = parser.parse_args()
  if os.environ.get("GITHUB_REPOSITORY") != REPO or (
    os.environ.get("GITHUB_REF") != "refs/heads/main"
  ):
    raise RuntimeError("not in owner-authorized disposable sandbox")
  if not args.run_id.startswith(
    "rwf97-" + os.environ["GITHUB_RUN_ID"] + "-"
  ):
    raise RuntimeError("test run identity not authorized")
  repo = github("")
  if repo["default_branch"] != "main":
    raise RuntimeError("unexpected sandbox default branch")
  src = github("git/ref/heads/rwf97-sandbox-source")
  dest = github("git/ref/heads/rwf97-sandbox-target")
  if src["object"]["sha"] != SHA or (
    dest["object"]["sha"] == SHA
  ):
    raise RuntimeError("unsafe source/target fixture")
  params = {
    "source_ref": SOURCE, "target_ref": TARGET,
    "expected_source_sha": SHA,
    "title": "RWF live probe " + args.run_id,
    "body": "Disposable adapter-created PR; never merge",
    "draft": True,
  }
  request = {
    "schema_version": 1, "operation": "pull_request.create",
    "repository": REPO, "request_id": args.run_id + "-create",
    "parameters": params,
  }
  created_pr = None
  try:
    first_code, first = invoke(request)
    if first_code or first["status"] != "applied":
      raise RuntimeError("real adapter PR create did not apply: "
                         + str(first))
    created_pr = first["result"]["number"]
    # Fresh subprocess verifies persistence and idempotent replay.
    again_code, again = invoke(request)
    if again_code or again["status"] != "unchanged" or (
      again["result"]["number"] != created_pr
    ):
      raise RuntimeError("PR create replay duplicated state")
    actual = github("pulls/" + str(created_pr))
    if (actual["state"] != "open" or actual["draft"] is not True
        or actual["title"] != params["title"]
        or actual["body"] != params["body"] + "\n" + (
          "<!-- RWF-HOST-REQUEST-V1:" +
          identity(request["operation"], request["request_id"]) +
          " -->"
        )
        or actual["head"]["sha"] != SHA
        or actual["head"]["ref"] != SOURCE.removeprefix("refs/heads/")
        or actual["base"]["ref"] != TARGET.removeprefix("refs/heads/")
        or actual["user"]["login"] != "github-actions[bot]"):
      raise RuntimeError("GitHub did not persist exact adapter PR")
    assert_reservation(request)

    reused = {**request, "parameters": {
      **params, "title": "CHANGED SAME-ID REQUEST",
    }}
    altered_code, altered = invoke(reused)
    if altered_code == 0 or altered["error"] != "conflict":
      raise RuntimeError("changed same-ID PR request not rejected")
    changed_sha = {**request,
      "request_id": args.run_id + "-stale-create",
      "parameters": {**params, "expected_source_sha": "0" * 40},
    }
    stale_code, stale = invoke(changed_sha)
    if stale_code == 0 or stale["error"] not in {
      "conflict", "unauthorized",
    }:
      raise RuntimeError("stale PR create head was not refused")
    print(json.dumps({
      "result": "PASS",
      "adapter": "shipped Python",
      "operation": "pull_request.create",
      "repository": REPO, "pr": created_pr,
      "first": first["status"],
      "restart_replay": again["status"],
      "changed_idempotency_input": "conflict",
      "stale_source_head": "rejected",
      "provider_persisted": True,
      "reservation_verified": True,
    }, sort_keys=True))
  finally:
    if created_pr is not None:
      # Fixture cleanup is not a #81 semantic pull_request.update.
      cleanup = subprocess.run([
        "gh", "api", "--method", "PATCH",
        f"repos/{REPO}/pulls/{created_pr}",
        "-f", "state=closed",
      ], capture_output=True, text=True, check=False, timeout=30)
      if cleanup.returncode or github(
        "pulls/" + str(created_pr)
      )["state"] != "closed":
        raise RuntimeError("disposable PR cleanup failed")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
