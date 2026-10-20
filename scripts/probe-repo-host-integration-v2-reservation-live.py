#!/usr/bin/env python3
"""#681 authenticated real GitHub interrupted create + fresh-process restart.

Disposable-000 only; never updates main or any production submission.
"""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "adapters"))
from repo_host_github_provider import (
  GitHubBackend, ProviderError, reservation_ref,
)
from repo_host_github_integration import (
  IntegrationProviderError, create_int_attempt,
)

REPO = "Ma-XX-oN/Disposable-000"


def get_sha(backend, ref):
  try:
    value = backend.get("git/ref/" + ref.removeprefix("refs/"))
  except ProviderError as error:
    if error.code == "not_found":
      return None
    raise
  if value.get("ref") != ref:
    raise RuntimeError("foreign provider ref response")
  return value["object"]["sha"]


def remove(backend, ref):
  if get_sha(backend, ref) is None:
    return
  result = subprocess.run(
    ["gh", "api", "--method", "DELETE",
     "repos/" + REPO + "/git/refs/" + ref.removeprefix("refs/")],
    capture_output=True, text=True, timeout=30, check=False)
  if result.returncode or get_sha(backend, ref) is not None:
    raise RuntimeError("ref cleanup unverified: " + ref)


def main():
  if os.environ.get("GITHUB_REPOSITORY") != REPO:
    raise RuntimeError("not authorized outside disposable repository")
  run_id = os.environ["GITHUB_RUN_ID"]
  if not run_id.isdecimal():
    raise RuntimeError("no provider run identity")
  one = GitHubBackend(REPO)
  if one.get("").get("full_name") != REPO:
    raise RuntimeError("repository identity mismatch")
  original = get_sha(one, "refs/heads/main")
  guid = str(uuid.uuid5(uuid.NAMESPACE_DNS, REPO + "/resume/" + run_id))
  ref = ("refs/heads/INT-ATTEMPT-issue-681/rwf681-recover-" +
         run_id + "-" + guid)
  request = {
    "schema_version": 2, "repository": REPO, "operation": "ref.create",
    "request_id": "sandbox-interrupted-" + run_id,
    "parameters": {"ref": ref, "sha": original},
  }
  reserved = reservation_ref(request)
  if get_sha(one, ref) or get_sha(one, reserved):
    raise RuntimeError("isolated provider namespace already occupied")
  try:
    # Stage 1: persist reservation only.  Simulates coordinator crash here.
    if one.reserve(request) is not True:
      raise AssertionError("expected new provider reservation")
    if get_sha(one, reserved) is None or get_sha(one, ref) is not None:
      raise AssertionError("crash boundary not represented on real GitHub")
    # Stage 2: entirely new provider instance reads reservation and resumes.
    after_restart = GitHubBackend(REPO)
    status, result = create_int_attempt(
      after_restart, request, authorized=True)
    if status != "applied" or result != {"ref": ref, "sha": original}:
      raise AssertionError("provider recovery failed after reservation crash")
    if get_sha(one, ref) != original:
      raise AssertionError("recovered publication not independently confirmed")
    replay_status, replay = create_int_attempt(
      GitHubBackend(REPO), request, authorized=True)
    if replay_status != "unchanged" or replay != result:
      raise AssertionError("idempotent restart failed")
    forged = {**request, "parameters": {"ref": ref, "sha": "f" * 40}}
    try:
      create_int_attempt(GitHubBackend(REPO), forged, authorized=True)
    except (ProviderError, IntegrationProviderError):
      pass
    else:
      raise AssertionError("same reserved request accepted changed source")
    if get_sha(one, "refs/heads/main") != original:
      raise AssertionError("disposable main moved")
  finally:
    errors = []
    for target in (ref, reserved):
      try:
        remove(one, target)
      except Exception:
        errors.append(target)
    if errors:
      raise RuntimeError("sandbox cleanup failed " + repr(errors))
  print(json.dumps({
    "result": "PASS", "repository": REPO, "guid": guid,
    "reservation_survives_process_restart": True,
    "recovered_ref_sha": original, "forged_replay_refused": True,
    "main_unchanged": True, "cleanup": "all sandbox refs absent",
  }, sort_keys=True))


if __name__ == "__main__":
  main()
