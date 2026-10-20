#!/usr/bin/env python3
"""#103 exact-source authenticated retirement acceptance in Disposable-000.

This is an isolated provider-landed fixture, NOT production authorization.
CI overlays exact #103 modules into certified #681 provider checkout.
Only run under the explicitly named disposable repository.
"""
import json
import os
from pathlib import Path
import re
import subprocess
from unittest.mock import patch
import uuid

from adapters.repo_host_github_provider import GitHubBackend, ProviderError
from adapters.repo_host_github_integration_terminal import (
  read_terminal, record_terminal, retirement_terminal_reader,
)
from adapters.repo_host_github_integration_retirement import (
  read_retirement, record_retirement,
)
from repo_workflow.prelim_retirement import (
  LandedIntegration, PrelimRetirementError,
)
from repo_workflow.prelim_retirement_github import verify_github_retirement
from repo_workflow.prelim_retirement_execute import retire_landed_attempt_ref
from repo_workflow.prelim_retirement_remote import retire_verified_ref

REPO = "Ma-XX-oN/Disposable-000"
SHA = re.compile(r"[0-9a-f]{40}\Z")


def git(root, *args):
  p = subprocess.run(["git", "-C", str(root), *args],
    check=True, capture_output=True, text=True, timeout=45)
  return p.stdout.strip()


def ref_read(backend, ref):
  try:
    value = backend.get("git/ref/" + ref.removeprefix("refs/"))
  except ProviderError as error:
    if error.code == "not_found":
      return None
    raise
  if value.get("ref") != ref:
    raise RuntimeError("provider returned wrong reference")
  return value["object"]["sha"]


def compare(backend, old, new):
  return (backend.get("compare/" + old + "..." + new)
          ["merge_base_commit"]["sha"] == old)


def cleanup_ref(backend, ref):
  existing = ref_read(backend, ref)
  if existing is None:
    return
  # These refs are constructed from this workflow's GUID and destination.
  result = subprocess.run(["gh", "api", "--method", "DELETE",
    "repos/" + REPO + "/git/refs/" + ref.removeprefix("refs/")],
    capture_output=True, text=True, timeout=30)
  if result.returncode or ref_read(backend, ref) is not None:
    raise RuntimeError("disposable cleanup failed for " + ref)


def main():
  if os.environ.get("GITHUB_REPOSITORY") != REPO:
    raise RuntimeError("refuse non-disposable repository")
  run_id = os.environ["GITHUB_RUN_ID"]
  if not run_id.isdecimal():
    raise RuntimeError("invalid hosted run ID")
  root = Path(os.environ["RWF_DISPOSABLE_CHECKOUT"]).resolve()
  backend = GitHubBackend(REPO)
  if backend.get("").get("full_name") != REPO:
    raise RuntimeError("authenticated repository differs")
  if git(root, "remote", "get-url", "origin") != (
      "https://github.com/" + REPO + ".git"):
    raise RuntimeError("remote not bound to disposable provider")

  guid = str(uuid.uuid5(uuid.NAMESPACE_DNS,
    REPO + "/rwf103-acceptance/" + run_id))
  sibling_guid = str(uuid.uuid5(uuid.NAMESPACE_DNS,
    REPO + "/rwf103-sibling/" + run_id))
  destination_name = "rwf103-landed-" + run_id
  destination = "refs/heads/" + destination_name
  prelim = ("refs/heads/PRELIM-issue-103/" + destination_name +
            "-" + guid)
  attempt = ("refs/heads/INT-ATTEMPT-issue-103/" + destination_name +
             "-" + guid)
  sibling = ("refs/heads/PRELIM-issue-103/" + destination_name +
             "-" + sibling_guid)
  sibling_int = ("refs/heads/INT-ATTEMPT-issue-103/" +
                 destination_name + "-" + sibling_guid)
  terminal_tag = "refs/tags/rwf-integration-terminal-v2-" + guid
  retire_tags = [
    "refs/tags/rwf-integration-ref-retired-v2-" + guid + "-prelim",
    "refs/tags/rwf-integration-ref-retired-v2-" + guid + "-int-attempt",
  ]
  owned = [prelim, attempt, sibling, sibling_int,
           *retire_tags, terminal_tag, destination]
  if any(ref_read(backend, ref) is not None for ref in owned):
    raise RuntimeError("isolated provider namespace already occupied")

  before_main = ref_read(backend, "refs/heads/main")
  if not isinstance(before_main, str) or SHA.fullmatch(before_main) is None:
    raise RuntimeError("disposable main unavailable")
  tree = git(root, "rev-parse", before_main + "^{tree}")
  landed_sha = git(root,
    "-c", "user.name=RWF 103 Acceptance",
    "-c", "user.email=repoworkflow@users.noreply.github.com",
    "commit-tree", tree, "-p", before_main,
    "-m", "isolated RWF #103 landed fixture " + guid)
  if SHA.fullmatch(landed_sha) is None:
    raise RuntimeError("invalid fixture landing SHA")

  primary_error = None
  result = {}
  try:
    git(root, "push", "origin", landed_sha + ":" + destination)
    if ref_read(backend, destination) != landed_sha:
      raise RuntimeError("provider landing ref not committed")
    for ref in (prelim, attempt, sibling, sibling_int):
      backend.post("git/refs", {"ref": ref, "sha": before_main})
    if any(ref_read(backend, ref) != before_main for ref in (
        prelim, attempt, sibling, sibling_int)):
      raise RuntimeError("provider fixture ref readback failed")

    terminal = {
      "repository": REPO, "guid": guid,
      "status": "integrated", "prelim_ref": prelim,
      "prelim_sha": before_main, "int_attempt_ref": attempt,
      "accepted_sha": before_main, "destination_ref": destination,
      "expected_destination_sha": before_main,
      "observed_destination_sha": landed_sha,
      "landed_sha": landed_sha, "integration_id": "rwf103-" + run_id,
      "provider_operation_id": "fixture-" + run_id,
      "umbrella": "issue-103",
      "terminal_evidence_ref": "rwf103-provider-" + run_id,
    }
    def verified_terminal(value):
      return (
        value == terminal
        and ref_read(backend, prelim) == before_main
        and ref_read(backend, attempt) == before_main
        and ref_read(backend, destination) == landed_sha
        and compare(backend, before_main, landed_sha)
        and ref_read(backend, "refs/heads/main") == before_main
      )
    published, obj = record_terminal(
      backend, terminal, authorized=True,
      verify_evidence=verified_terminal)
    if published != "applied" or obj["record"] != terminal:
      raise RuntimeError("terminal not independently persisted")
    if read_terminal(GitHubBackend(REPO), guid) != terminal:
      raise RuntimeError("fresh provider cannot read terminal")

    landed = LandedIntegration(
      prelim, before_main, attempt, before_main, destination,
      landed_sha, terminal["integration_id"],
      terminal["terminal_evidence_ref"])
    fresh = GitHubBackend(REPO)
    reader = retirement_terminal_reader(fresh, landed)
    plan = verify_github_retirement(fresh, landed, reader)
    if not plan.eligible_for_ref_retirement:
      raise RuntimeError("landed provider proof not eligible")

    # Wrong expected SHA and sibling attempt MUST fail without deleting refs.
    try:
      retire_verified_ref(root, "origin", plan, prelim, landed_sha,
        backend=fresh, landed=landed, read_terminal=reader)
    except PrelimRetirementError:
      pass
    else:
      raise RuntimeError("wrong accepted SHA was allowed")
    try:
      retire_verified_ref(root, "origin", plan, sibling, before_main,
        backend=fresh, landed=landed, read_terminal=reader)
    except PrelimRetirementError:
      pass
    else:
      raise RuntimeError("sibling ref deletion was allowed")

    # A failed provider push is UNKNOWN and leaves all original refs intact.
    original = subprocess.run
    def lost_before_push(args, **kwargs):
      if "push" in args:
        raise subprocess.TimeoutExpired(args, 30)
      return original(args, **kwargs)
    with patch("repo_workflow.prelim_retirement_remote.subprocess.run",
               side_effect=lost_before_push):
      try:
        retire_landed_attempt_ref(root=root, remote="origin",
          backend=fresh, landed=landed, read_terminal=reader,
          ref_kind="PRELIM")
      except PrelimRetirementError as error:
        if "UNKNOWN" not in str(error):
          raise
      else:
        raise RuntimeError("uncertain provider push accepted")
    if ref_read(backend, prelim) != before_main:
      raise RuntimeError("UNKNOWN altered published PRELIM")

    for kind, ref in (("PRELIM", prelim), ("INT-ATTEMPT", attempt)):
      trusted = GitHubBackend(REPO)
      callback = retirement_terminal_reader(trusted, landed)
      deleted = retire_landed_attempt_ref(
        root=root, remote="origin", backend=trusted,
        landed=landed, read_terminal=callback, ref_kind=kind)
      if (not deleted.absent_after or
          deleted.previously_observed_sha != before_main or
          ref_read(backend, ref) is not None):
        raise RuntimeError("conditional deletion not verified: " + kind)
      audit = {
        "repository": REPO, "guid": guid, "ref_kind": kind,
        "retired_ref": ref, "expected_sha": before_main,
        "operation_id": "rwf103-" + kind.lower() + "-" + run_id,
        "terminal_evidence_ref": terminal["terminal_evidence_ref"],
        "destination_ref": destination, "landed_sha": landed_sha,
        "outcome": "retired",
      }
      def verify_deletion(record):
        return (
          record == audit
          and deleted.ref == ref and deleted.absent_after
          and ref_read(backend, ref) is None
          and read_terminal(GitHubBackend(REPO), guid) == terminal
          and ref_read(backend, destination) == landed_sha)
      state, persisted = record_retirement(
        GitHubBackend(REPO), audit, verify_deletion=verify_deletion)
      if state != "applied" or persisted != audit:
        raise RuntimeError("retirement audit not applied")
      if read_retirement(GitHubBackend(REPO), guid, kind) != audit:
        raise RuntimeError("audit not persisted across fresh provider")
      replay, old = record_retirement(GitHubBackend(REPO), audit,
        verify_deletion=verify_deletion)
      if replay != "unchanged" or old != audit:
        raise RuntimeError("retirement audit replay not idempotent")

    if any(ref_read(backend, ref) != before_main
           for ref in (sibling, sibling_int)):
      raise RuntimeError("sibling attempt mutated by retirement")
    if read_terminal(GitHubBackend(REPO), guid) != terminal:
      raise RuntimeError("terminal record lost after retirement")
    if ref_read(backend, "refs/heads/main") != before_main:
      raise RuntimeError("disposable main was altered")
    result = {
      "result": "PASS", "source": "RWF #103 exact source checkout",
      "repository": REPO, "guid": guid,
      "provider_landed_sha": landed_sha,
      "retired": ["PRELIM", "INT-ATTEMPT"],
      "terminal_restart": "PASS",
      "audit_restart_and_idempotency": "PASS",
      "negative_unknown_and_sibling": "PASS",
      "main_unchanged": True,
    }
  except Exception as error:
    primary_error = str(error)
  cleanup_errors = []
  for ref in owned:
    try:
      cleanup_ref(backend, ref)
    except Exception:
      cleanup_errors.append(ref)
  if primary_error or cleanup_errors:
    raise RuntimeError(json.dumps({
      "result": "FAIL", "error": primary_error,
      "cleanup_errors": cleanup_errors}, sort_keys=True))
  print(json.dumps({**result, "cleanup": "verified absent"},
                   sort_keys=True))


if __name__ == "__main__":
  main()
