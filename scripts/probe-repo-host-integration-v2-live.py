#!/usr/bin/env python3
"""Real disposable-only #681 provider create/CAS/lease acceptance.

This script NEVER runs against RepoWorkflow or an arbitrary repository.
No protected main, issue, pull request, READY branch or stable tag is updated.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "adapters"))

from repo_host_github_provider import (
  GitHubBackend, ProviderError, reservation_ref,
)
from repo_host_github_integration import (
  IntegrationProviderError, cas_int_attempt_git, create_int_attempt,
)
from repo_host_github_integration_lease import (
  LeaseProviderError, _ref as lease_ref, cas_lease, read_lease,
)


REPO = "Ma-XX-oN/Disposable-000"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_GUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")


def git(root, *argv):
  result = subprocess.run(
    ["git", "-C", str(root), *argv], capture_output=True,
    text=True, timeout=45, check=False,
  )
  if result.returncode:
    raise RuntimeError("isolated Git fixture command failed: " + argv[0])
  return result.stdout.strip()


def present(backend, ref):
  try:
    response = backend.get("git/ref/" + ref.removeprefix("refs/"))
  except ProviderError as error:
    if error.code == "not_found":
      return None
    raise
  if (type(response) is not dict or response.get("ref") != ref
      or type(response.get("object")) is not dict):
    raise RuntimeError("provider returned a foreign ref identity")
  sha = response["object"].get("sha")
  if type(sha) is not str or _SHA.fullmatch(sha) is None:
    raise RuntimeError("provider ref has invalid commit SHA")
  return sha


def no_existing(backend, refs):
  if any(present(backend, ref) is not None for ref in refs):
    raise RuntimeError("sandbox acceptance namespace already exists")


def write_commit(root, parent, label):
  tree = git(root, "rev-parse", parent + "^{tree}")
  sha = git(root, "-c", "user.name=RepoWorkflow",
            "-c", "user.email=repoworkflow@users.noreply.github.com",
            "commit-tree", tree, "-p", parent, "-m", label)
  if _SHA.fullmatch(sha) is None:
    raise RuntimeError("isolated candidate commit invalid")
  return sha


def delete_ref(ref):
  # Caller supplies only refs created under this run's private namespace.
  suffix = ref.removeprefix("refs/")
  command = ["gh", "api", "--method", "DELETE",
             "repos/" + REPO + "/git/refs/" + suffix]
  return subprocess.run(
    command, capture_output=True, text=True, timeout=30,
    check=False,
  ).returncode == 0


def request(operation, request_id, parameters):
  return {
    "schema_version": 2, "repository": REPO,
    "operation": operation, "request_id": request_id,
    "parameters": parameters,
  }


def run(root, backend, guid, destination):
  ref_dest = "refs/heads/" + destination
  ref_int = ("refs/heads/INT-ATTEMPT-issue-681/" +
             destination + "-" + guid)
  base = present(backend, "refs/heads/main")
  if base is None:
    raise RuntimeError("sandbox default branch missing")
  created = []
  op = "rwf681-live-" + guid
  create_request = request("ref.create", op + "-create",
                           {"ref": ref_int, "sha": base})
  reservation = reservation_ref(create_request)
  lease = lease_ref(REPO, destination)
  refs = [ref_int, ref_dest, reservation, lease]
  no_existing(backend, refs)

  def cleanup():
    errors = []
    for ref in (ref_int, reservation, lease, ref_dest):
      try:
        if present(backend, ref) is not None and not delete_ref(ref):
          errors.append(ref)
        if present(backend, ref) is not None:
          errors.append("still present: " + ref)
      except Exception:
        errors.append("unknown cleanup: " + ref)
    return errors

  error = None
  details = {}
  try:
    backend.post("git/refs", {"ref": ref_dest, "sha": base})
    created.append(ref_dest)
    if present(backend, ref_dest) != base:
      raise RuntimeError("sandbox destination readback changed")

    status, evidence = create_int_attempt(
      backend, create_request, authorized=True)
    if status != "applied" or evidence != {"ref": ref_int, "sha": base}:
      raise RuntimeError("INT-ATTEMPT initial creation unverified")
    created.extend([ref_int, reservation])
    status, evidence = create_int_attempt(
      backend, create_request, authorized=True)
    if status != "unchanged" or evidence["sha"] != base:
      raise RuntimeError("exact ref creation retry was not idempotent")

    accepted = write_commit(root, base, op + "-accepted")
    sibling = write_commit(root, base, op + "-stale")
    result = cas_int_attempt_git(root, "origin", ref_int, base, accepted)
    if result != {"ref": ref_int, "sha": accepted}:
      raise RuntimeError("INT-ATTEMPT CAS result identity mismatch")
    if present(backend, ref_int) != accepted:
      raise RuntimeError("INT-ATTEMPT CAS provider readback differs")
    try:
      cas_int_attempt_git(root, "origin", ref_int, base, sibling)
    except IntegrationProviderError:
      pass
    else:
      raise RuntimeError("stale competing INT-ATTEMPT CAS succeeded")
    if present(backend, ref_int) != accepted:
      raise RuntimeError("stale contender moved accepted INT-ATTEMPT")

    if read_lease(backend, destination) != {
        "destination": destination, "generation": 0,
        "holder": None, "guid": None}:
      raise RuntimeError("initial destination lease not unowned")
    claimant = request("lease.cas", op + "-lease-1", {
      "destination": destination, "expected_generation": 0,
      "expected_holder": None, "expected_guid": None,
      "holder": op, "guid": guid,
    })
    status, lease1 = cas_lease(backend, claimant, root, "origin")
    if status != "applied" or lease1["generation"] != 1:
      raise RuntimeError("provider lease claim not confirmed")
    created.append(lease)
    try:
      cas_lease(backend, {
        **claimant, "request_id": op + "-stale-claim",
        "parameters": {
          **claimant["parameters"], "holder": op + "-other",
        },
      }, root, "origin")
    except LeaseProviderError:
      pass
    else:
      raise RuntimeError("competing stale destination lease claimed")
    if read_lease(backend, destination) != lease1:
      raise RuntimeError("stale lease actor changed owner")

    release = request("lease.cas", op + "-release", {
      "destination": destination, "expected_generation": 1,
      "expected_holder": op, "expected_guid": guid,
      "holder": None, "guid": None,
    })
    status, lease2 = cas_lease(backend, release, root, "origin")
    if status != "applied" or lease2 != {
        "destination": destination, "generation": 2,
        "holder": None, "guid": None}:
      raise RuntimeError("provider lease release/restart result invalid")

    details = {
      "repository": REPO, "attempt": guid,
      "destination": destination,
      "accepted_int_sha": accepted,
      "stale_int_sha": sibling,
      "lease_generation": lease2["generation"],
      "create_replayed": True, "stale_cas_refused": True,
      "stale_lease_refused": True,
    }
  except Exception as failure:
    error = str(failure)
  cleanup_errors = cleanup()
  if error or cleanup_errors:
    raise RuntimeError(json.dumps({
      "result": "FAIL", "experiment_error": error,
      "cleanup_errors": cleanup_errors,
      "created_refs": created,
    }, sort_keys=True))
  print(json.dumps({**details, "result": "PASS",
                    "cleanup": "all isolated refs deleted"}, sort_keys=True))


def main():
  if os.environ.get("GITHUB_REPOSITORY") != REPO:
    raise RuntimeError("this live mutation probe is disposable-repository only")
  run_id = os.environ.get("GITHUB_RUN_ID", "")
  if not run_id.isdecimal() or int(run_id) < 1:
    raise RuntimeError("authenticated workflow identity unavailable")
  guid = str(uuid.uuid5(uuid.NAMESPACE_DNS,
                        REPO + "/rwf681/" + run_id))
  assert _GUID.fullmatch(guid)
  dest = "rwf681-test-" + run_id
  root = Path(os.environ["RWF_DISPOSABLE_CHECKOUT"]).resolve()
  backend = GitHubBackend(REPO)
  details = backend.get("")
  if details.get("full_name") != REPO:
    raise RuntimeError("authenticated provider repository differs")
  remote = git(root, "remote", "get-url", "origin")
  if remote != details["clone_url"]:
    raise RuntimeError("Git effective remote differs from provider clone URL")
  if git(root, "remote", "get-url", "--push", "origin") != remote:
    raise RuntimeError("Git push remote is different from authenticated fetch")
  run(root, backend, guid, dest)


if __name__ == "__main__":
  main()
