#!/usr/bin/env python3
"""#681 real disposable provider terminal, conditional cleanup and audit.

Uses only GUID-scoped disposable branches and tags. No protected main changes.
This probes primitives; its verifier is an isolated test oracle, not deployment
of independent production authorization.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "adapters"))
sys.path.insert(0, str(ROOT))

from repo_host_github_provider import GitHubBackend, ProviderError
from repo_host_github_integration_terminal import (
  record_terminal, read_terminal,
)
from repo_host_github_integration_retirement import (
  record_retirement, read_retirement, RetirementAuditError,
)


REPOSITORY = "Ma-XX-oN/Disposable-000"
_SHA = re.compile(r"[0-9a-f]{40}\Z")


def git(root, *args, allow_failure=False):
  result = subprocess.run(
    ["git", "-C", str(root), *args], capture_output=True,
    text=True, timeout=45, check=False,
  )
  if result.returncode and not allow_failure:
    raise RuntimeError("sandbox Git operation failed: " + args[0])
  return result


def sha(root, *args):
  return git(root, *args).stdout.strip()


def get_ref(backend, ref):
  try:
    value = backend.get("git/ref/" + ref.removeprefix("refs/"))
  except ProviderError as error:
    if error.code == "not_found":
      return None
    raise
  if value.get("ref") != ref:
    raise RuntimeError("provider returned another ref")
  return value["object"]["sha"]


def delete_exact(backend, ref, expected):
  if get_ref(backend, ref) != expected:
    raise RuntimeError("cleanup ref identity does not match")
  result = subprocess.run(
    ["gh", "api", "--method", "DELETE",
     "repos/" + REPOSITORY + "/git/refs/" + ref.removeprefix("refs/")],
    capture_output=True, text=True, timeout=30, check=False,
  )
  if result.returncode or get_ref(backend, ref) is not None:
    raise RuntimeError("disposable ref cleanup not confirmed")


def main():
  if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
    raise RuntimeError("must execute in disposable GitHub repository")
  root = Path(os.environ["RWF_DISPOSABLE_CHECKOUT"]).resolve()
  run_id = os.environ["GITHUB_RUN_ID"]
  if not run_id.isdecimal():
    raise RuntimeError("no authoritative run identity")
  guid = str(uuid.uuid5(uuid.NAMESPACE_DNS,
                        REPOSITORY + "/rwf681-terminal/" + run_id))
  dest = "rwf681-terminal-" + run_id
  prefix = "issue-681"
  destination = "refs/heads/" + dest
  prelim = "refs/heads/PRELIM-" + prefix + "/" + dest + "-" + guid
  attempt = "refs/heads/INT-ATTEMPT-" + prefix + "/" + dest + "-" + guid
  terminal_ref = "refs/tags/rwf-integration-terminal-v2-" + guid
  retired_prelim = ("refs/tags/rwf-integration-ref-retired-v2-"
                    + guid + "-prelim")
  retired_int = ("refs/tags/rwf-integration-ref-retired-v2-"
                 + guid + "-int-attempt")
  owned = [prelim, attempt, terminal_ref, retired_prelim,
           retired_int, destination]
  backend = GitHubBackend(REPOSITORY)
  if backend.get("").get("full_name") != REPOSITORY:
    raise RuntimeError("provider repository changed")
  if any(get_ref(backend, ref) is not None for ref in owned):
    raise RuntimeError("disposable test namespace not empty")
  baseline = get_ref(backend, "refs/heads/main")
  if type(baseline) is not str or _SHA.fullmatch(baseline) is None:
    raise RuntimeError("disposable baseline unavailable")
  tree = sha(root, "rev-parse", baseline + "^{tree}")
  landed = sha(root, "-c", "user.name=RepoWorkflow",
               "-c", "user.email=repoworkflow@users.noreply.github.com",
               "commit-tree", tree, "-p", baseline, "-m",
               "RWF #681 isolated landed fixture " + guid)
  if _SHA.fullmatch(landed) is None:
    raise RuntimeError("landed fixture malformed")
  failure = None
  summary = {}
  try:
    git(root, "push", "origin", landed + ":" + destination)
    if get_ref(backend, destination) != landed:
      raise RuntimeError("isolated destination not landed")
    for ref in (prelim, attempt):
      backend.post("git/refs", {"ref": ref, "sha": baseline})
      if get_ref(backend, ref) != baseline:
        raise RuntimeError("isolated source ref missing")
    record = {
      "repository": REPOSITORY, "guid": guid,
      "status": "integrated", "prelim_ref": prelim,
      "prelim_sha": baseline, "int_attempt_ref": attempt,
      "accepted_sha": baseline, "destination_ref": destination,
      "expected_destination_sha": baseline,
      "observed_destination_sha": landed, "landed_sha": landed,
      "provider_operation_id": "sandbox-merge-" + run_id,
      "umbrella": prefix, "integration_id": "sandbox-" + run_id,
      "terminal_evidence_ref": "sandbox-verified-" + run_id,
    }

    def independently_check(value):
      return (
        value == record
        and get_ref(backend, prelim) == baseline
        and get_ref(backend, attempt) == baseline
        and get_ref(backend, destination) == landed
        and backend.get("compare/" + baseline + "..." +
                        landed)["merge_base_commit"]["sha"] == baseline
      )

    status, returned = record_terminal(
      backend, record, authorized=True,
      verify_evidence=independently_check)
    if status != "applied" or returned["record"] != record:
      raise RuntimeError("terminal provider publication not applied")
    if read_terminal(backend, guid) != record:
      raise RuntimeError("terminal independent provider read differs")
    status, _ = record_terminal(
      backend, record, authorized=True,
      verify_evidence=independently_check)
    if status != "unchanged":
      raise RuntimeError("immutable terminal replay wrote again")
    try:
      record_terminal(
        backend, {**record, "integration_id": "forged"},
        authorized=True, verify_evidence=lambda _: True)
    except Exception:
      pass
    else:
      raise RuntimeError("conflicting terminal record accepted")

    for kind, ref in (("PRELIM", prelim), ("INT-ATTEMPT", attempt)):
      proof = {
        "repository": REPOSITORY, "guid": guid, "ref_kind": kind,
        "retired_ref": ref, "expected_sha": baseline,
        "operation_id": "sandbox-retire-" + kind.lower() + "-" + run_id,
        "terminal_evidence_ref": record["terminal_evidence_ref"],
        "destination_ref": destination, "landed_sha": landed,
        "outcome": "retired",
      }
      try:
        record_retirement(
          backend, proof, verify_deletion=lambda _: True)
      except RetirementAuditError:
        pass
      else:
        raise RuntimeError("retirement accepted before conditional deletion")
      push = git(
        root, "push", "--porcelain",
        "--force-with-lease=" + ref + ":" + baseline,
        "origin", ":" + ref,
      )
      if push.returncode or get_ref(backend, ref) is not None:
        raise RuntimeError("conditional ref retirement unverified")
      status, audit = record_retirement(
        backend, proof,
        verify_deletion=lambda x: (
          x == proof and read_terminal(backend, guid) == record
          and get_ref(backend, x["retired_ref"]) is None
          and get_ref(backend, destination) == landed),
      )
      if status != "applied" or audit != proof:
        raise RuntimeError("audited retirement publication unverified")
      if read_retirement(backend, guid, kind) != proof:
        raise RuntimeError("durable retirement readback differs")
      status, audit = record_retirement(
        backend, proof,
        verify_deletion=lambda _: True)
      if status != "unchanged" or audit != proof:
        raise RuntimeError("audit replay not immutable")
    if get_ref(backend, "refs/heads/main") != baseline:
      raise RuntimeError("sandbox main changed during test")
    summary = {
      "result": "PASS", "repository": REPOSITORY, "guid": guid,
      "landed_sha": landed, "terminal": "persisted/replayed",
      "retirements": "PRELIM and INT-ATTEMPT separately audited",
      "main_unchanged": True,
    }
  except Exception as error:
    failure = str(error)
  cleanup_errors = []
  for ref in owned:
    try:
      existing = get_ref(backend, ref)
      if existing is not None:
        delete_exact(backend, ref, existing)
    except Exception:
      cleanup_errors.append(ref)
  if failure or cleanup_errors:
    raise RuntimeError(json.dumps({
      "result": "FAIL", "reason": failure,
      "cleanup_errors": cleanup_errors,
    }, sort_keys=True))
  print(json.dumps({**summary, "cleanup": "verified absent"},
                   sort_keys=True))


if __name__ == "__main__":
  main()
