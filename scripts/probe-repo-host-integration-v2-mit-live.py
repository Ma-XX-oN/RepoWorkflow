#!/usr/bin/env python3
"""#681 disposable GitHub MIT persist/defer/resume/revoke/restart acceptance.

Creates only GUID-scoped audit tags and a disposable destination ref.
The injected test oracle is NOT a production independent authority.
"""
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "adapters"))

from repo_host_github_provider import GitHubBackend, ProviderError
from adapters.repo_host_github_integration_mit import (
  MitProviderError, read_mit, record_mit,
)

REPO = "Ma-XX-oN/Disposable-000"


def get_ref(backend, ref):
  try:
    value = backend.get("git/ref/" + ref.removeprefix("refs/"))
  except ProviderError as error:
    if error.code == "not_found":
      return None
    raise
  if value["ref"] != ref:
    raise AssertionError("foreign provider ref")
  return value["object"]["sha"]


def delete_ref(ref):
  import subprocess
  result = subprocess.run([
    "gh", "api", "--method", "DELETE",
    "repos/" + REPO + "/git/refs/" + ref.removeprefix("refs/"),
  ], check=False, capture_output=True, text=True, timeout=40)
  if result.returncode:
    raise RuntimeError("disposable GitHub cleanup rejected " + ref)


def must_refuse(action, label):
  try:
    action()
  except (MitProviderError, ProviderError):
    return
  raise AssertionError("unsafe provider acceptance: " + label)


class LostReply:
  """Separate actor which loses the ACK only after GitHub accepted the write."""
  def __init__(self, repository):
    self.inner = GitHubBackend(repository)
    self.repository = repository
    self.drop = True

  def get(self, *args, **kwargs):
    return self.inner.get(*args, **kwargs)

  def post(self, route, value):
    persisted = self.inner.post(route, value)
    if route == "git/refs" and self.drop:
      self.drop = False
      raise RuntimeError("synthetic lost ACK after real GitHub POST")
    return persisted


def main():
  if os.environ.get("GITHUB_REPOSITORY") != REPO:
    raise RuntimeError("must execute in disposable repository")
  run_id = os.environ["GITHUB_RUN_ID"]
  if not run_id.isdecimal():
    raise RuntimeError("authenticated Actions run ID absent")
  guid = str(uuid.uuid5(uuid.NAMESPACE_DNS, REPO + "/mit/" + run_id))
  dest = "rwf681-mit-" + run_id
  dest_ref = "refs/heads/" + dest
  prelim = "refs/heads/PRELIM-issue-681/" + dest + "-" + guid
  backend = GitHubBackend(REPO)
  if backend.get("").get("full_name") != REPO:
    raise RuntimeError("repository authentication mismatch")
  original_main = get_ref(backend, "refs/heads/main")
  owned = [dest_ref, prelim]
  for kind, generation in (
      ("deferred", 1), ("resume", 2), ("resume-revoke", 2),
      ("deferred", 3), ("resume", 4)):
    owned.append("refs/tags/rwf-mit-" + kind + "-v2-" +
                 guid + "-" + str(generation).zfill(12))
  if any(get_ref(backend, ref) is not None for ref in owned):
    raise RuntimeError("disposable namespace not initially empty")
  evidence = {}
  try:
    for ref in (dest_ref, prelim):
      backend.post("git/refs", {"ref": ref, "sha": original_main})
      if get_ref(backend, ref) != original_main:
        raise AssertionError("sandbox fixture not persisted")

    def defer(generation):
      return {
        "repository": REPO, "guid": guid, "destination": dest,
        "prelim_sha": original_main, "lease_generation": generation,
        "evidence_ref": "independent-fixture-defer-" + str(generation),
        "reason": "timeout",
      }

    def resume(generation, deferred_generation, approved=True):
      return {
        "repository": REPO, "guid": guid, "destination": dest,
        "prelim_sha": original_main, "expected_generation": generation,
        "deferred_evidence_ref":
          "independent-fixture-defer-" + str(deferred_generation),
        "evidence_ref": "fixture-" + (
          "approved-" if approved else "revoked-") + str(generation),
        "approved": approved,
      }

    # No unconditional approval, and no verifier means no publication.
    must_refuse(lambda: record_mit(
      backend, "resume", resume(2, 1), verify_evidence=lambda r: True),
      "approval without persisted defer")
    must_refuse(lambda: record_mit(
      backend, "deferred", defer(1), verify_evidence=None),
      "unverified defer")

    # Real GitHub publication, then lose the ACK; a new backend reconciles it.
    lost = LostReply(REPO)
    status, value = record_mit(
      lost, "deferred", defer(1), verify_evidence=lambda r: (
        r == defer(1) and get_ref(backend, prelim) == original_main))
    if status != "unchanged" or value != defer(1):
      raise AssertionError("real lost-response reconciliation failed")
    restarted = GitHubBackend(REPO)
    if read_mit(restarted, "deferred", guid, dest) != defer(1):
      raise AssertionError("restart lost persisted deferral")
    evidence["lost_ack"] = True

    must_refuse(lambda: record_mit(
      backend, "resume", resume(2, 99),
      verify_evidence=lambda r: True), "forged prior evidence")
    if read_mit(restarted, "resume", guid, dest) is not None:
      raise AssertionError("forged resume persisted")

    status, value = record_mit(
      backend, "resume", resume(2, 1),
      verify_evidence=lambda r: r == resume(2, 1))
    if status != "applied" or value != resume(2, 1):
      raise AssertionError("resume approval not persisted")
    if read_mit(GitHubBackend(REPO), "resume", guid, dest) != resume(2, 1):
      raise AssertionError("restart lost approved status")

    status, value = record_mit(
      backend, "resume", resume(2, 1, False),
      verify_evidence=lambda r: r == resume(2, 1, False))
    if status != "applied" or value != resume(2, 1, False):
      raise AssertionError("revocation not persisted")
    if read_mit(GitHubBackend(REPO), "resume", guid, dest)["approved"]:
      raise AssertionError("revoked grant read as approved")
    must_refuse(lambda: record_mit(
      backend, "resume", resume(2, 1),
      verify_evidence=lambda r: True), "reapproval after revocation")
    evidence["revocation"] = True

    if record_mit(
        backend, "deferred", defer(3),
        verify_evidence=lambda r: r == defer(3))[0] != "applied":
      raise AssertionError("second defer not persisted")
    must_refuse(lambda: record_mit(
      backend, "resume", resume(4, 1),
      verify_evidence=lambda r: True), "stale defer evidence")
    latest = resume(4, 3)
    if record_mit(
        backend, "resume", latest,
        verify_evidence=lambda r: r == latest)[0] != "applied":
      raise AssertionError("fresh resume not persisted")
    if read_mit(GitHubBackend(REPO), "resume", guid, dest) != latest:
      raise AssertionError("fresh restart approval not returned")
    must_refuse(lambda: record_mit(
      backend, "deferred", defer(3) | {"reason": "awaiting-manual"},
      verify_evidence=lambda r: True), "same-generation competing actor")
    if read_mit(backend, "deferred", guid, dest) != defer(3):
      raise AssertionError("collision modified existing defer")
    if get_ref(backend, "refs/heads/main") != original_main:
      raise AssertionError("protected main changed")
    evidence["second_defer_and_restart"] = True
  finally:
    errors = []
    for ref in reversed(owned):
      try:
        if get_ref(backend, ref) is not None:
          delete_ref(ref)
        if get_ref(backend, ref) is not None:
          errors.append(ref)
      except Exception:
        errors.append(ref)
    if errors:
      raise RuntimeError("disposable cleanup incomplete: " + repr(errors))
  print(json.dumps({
    "result": "PASS", "repository": REPO, "guid": guid,
    "main_unchanged": True, "cleanup": "all sandbox refs deleted",
    **evidence,
  }, sort_keys=True))


if __name__ == "__main__":
  main()
