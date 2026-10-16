"""Immutable exact-candidate PRELIM validation and acceptance (#102).

A PRELIM construction record is not accepted evidence. Hosted terminal
publication (#569-#572) remains the only tag publisher.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import re
import uuid

from .git import git
from .hosted_terminal_binding import bind_hosted_terminal
from .phase_terminal import plan_phase
from .prelim_attempt import (\n  PrelimError, _remote_ref, _restore_remote_record, _trusted_inputs,\n)
from .prelim_identity import validate_attempt
from .prelim_publication import (
  publish_identity, publish_validation, restore_identity, restore_validation,
)
from .state_store import StateStoreError, durable_store
from .terminal_tag import _remote_target
from .version_adapter import read_version

_SHA = re.compile(r"[0-9a-f]{40}\Z")


class PrelimValidationError(ValueError):
  """Candidate, provider evidence or immutable identity is inconsistent."""


@dataclass(frozen=True)
class HostedObservation:
  root: Path
  invocation: str
  run_id: int
  canonical_log: Path


@dataclass(frozen=True)
class PrelimValidation:
  attempt: str
  candidate_sha: str
  outcome: str
  identity_version: str | None
  revision: int


def _immutable(store, key: str, payload: dict, writer) -> dict:
  """Atomic first-writer identity; exact retries never allocate another."""
  try:
    existing = store.read(key)
  except StateStoreError as error:
    if "record is missing:" not in str(error):
      raise
    try:
      return store.create(key, payload, writer)
    except StateStoreError as race:
      if "record already exists:" not in str(race):
        raise
      existing = store.read(key)
  if existing["value"] != payload:
    raise PrelimValidationError("immutable PRELIM evidence identity conflict")
  return existing


def _observation(stage: str, candidate: str, item: HostedObservation) -> dict:
  if not isinstance(item, HostedObservation):
    raise PrelimValidationError("missing authenticated hosted observation")
  root = Path(item.root).resolve()
  log = Path(item.canonical_log).absolute()
  result = bind_hosted_terminal(
    root, stage=stage + "-testing", candidate=candidate,
    invocation=item.invocation, run_id=item.run_id, canonical_log=log,
  )
  if result is None:
    return {"outcome": "INCOMPLETE", "version": None, "tag": None}
  version = result["version"]
  outcome = result["outcome"]
  tag = plan_phase(version, phase=stage, outcome=outcome).terminal_tag
  # The existing #572 publisher must already have issued this immutable tag.
  # This code never creates, rewrites or promotes a Git tag.
  return {"outcome": outcome, "version": version, "tag": tag}


def validate_prelim(
  root: Path, attempt: str, config: dict, *,
  regression: HostedObservation, integration: HostedObservation,
) -> PrelimValidation:
  """Persist fail-closed provider evidence, accept only two authentic PASSes.

  Both terminal phase tags must identify the same *physical PRELIM candidate*
  SHA. Revalidation checks the current provider refs, not local main.
  """
  from .runtime_identity import runtime_writer_identity

  root = Path(root).resolve()
  try:
    attempt = str(uuid.UUID(attempt))
  except (ValueError, TypeError, AttributeError) as error:
    raise PrelimValidationError("invalid PRELIM attempt GUID") from error
  store = durable_store(root)
  remote = config["repository"]["authoritativeRemote"]
  try:
    recorded = _restore_remote_record(root, remote, store, attempt)
  except (PrelimError, StateStoreError) as error:
    raise PrelimValidationError("provider PRELIM attempt record rejected") from error
  if recorded is None:
    raise PrelimValidationError("provider PRELIM attempt record unavailable")
  record = store.read("prelim/attempts/" + attempt)
  if record != recorded:
    raise PrelimValidationError("provider PRELIM attempt record changed")
  value = record["value"]
  validate_attempt(value)
  if value["attempt"] != attempt or value["state"] != "ready":
    raise PrelimValidationError("PRELIM attempt is not ready")
  candidate = value["candidate_sha"]
  remote = config["repository"]["authoritativeRemote"]
  branch_ref = "refs/heads/" + value["branch"]

  def fresh() -> None:
    _trusted_inputs(
      root, remote, value["issue"], value["source_ref"],
      value["source_sha"], value["base_sha"], value["lifecycle_revision"],
    )
    if _remote_ref(root, remote, branch_ref) != candidate:
      raise PrelimValidationError("physical PRELIM candidate changed")
    if git(root, "cat-file", "-e", candidate + "^{commit}",
           check=False).returncode:
      raise PrelimValidationError("PRELIM candidate object unavailable")

  fresh()
  # Query the *physical candidate* through the configured repo adapter,
  # never the accepted task branch or a directly inspected VERSION file.
  with tempfile.TemporaryDirectory(prefix="rwf-prelim-version-") as temporary:
    workspace = Path(temporary) / "candidate"
    git(root, "worktree", "add", "--detach", str(workspace), candidate)
    try:
      actual_version = read_version(workspace, config)
      if actual_version != value["proposed_version"]:
        raise PrelimValidationError("candidate adapter version differs")
    finally:
      git(root, "worktree", "remove", "--force", str(workspace))
  checks = {
    "regression": _observation("regression", candidate, regression),
    "integration": _observation("integration", candidate, integration),
  }
  outcome = (
    "FAIL" if any(item["outcome"] == "FAIL" for item in checks.values())
    else "INCOMPLETE" if any(item["outcome"] == "INCOMPLETE"
                             for item in checks.values())
    else "PASS"
  )
  if outcome == "PASS":
    versions = {item["version"] for item in checks.values()}
    if len(versions) != 1:
      raise PrelimValidationError("terminal phases use different versions")
    for item in checks.values():
      if _remote_target(root, remote, item["tag"]) != candidate:
        raise PrelimValidationError("immutable provider tag has wrong target")
  fresh()
  payload = {
    "attempt": attempt, "issue": value["issue"],
    "candidate_sha": candidate, "source_sha": value["source_sha"],
    "base_sha": value["base_sha"], "proposed_version": value["proposed_version"],
    "regression": {**checks["regression"],
                   "invocation": regression.invocation, "run_id": regression.run_id},
    "integration": {**checks["integration"],
                    "invocation": integration.invocation, "run_id": integration.run_id},
    "outcome": outcome,
  }
  writer = runtime_writer_identity()
  # Each observation pair is an immutable audit entry; failed/incomplete
  # observations remain recorded even when a later retry succeeds.
  key = "prelim/validations/" + attempt + "/" + (
    regression.invocation + "-" + integration.invocation
  )
  restore_validation(root, remote, attempt, regression.invocation,
                     integration.invocation)
  audit = _immutable(store, key, payload, writer)
  publish_validation(root, remote, attempt, regression.invocation,
                     integration.invocation, audit, value["base_sha"])
  if outcome == "PASS":
    # Provider run IDs belong to per-observation audit, not to a stable
    # candidate identity: another matching verification is an idempotent
    # readback, not a new immutable PRELIM candidate.
    identity_payload = {
      "attempt": attempt, "issue": value["issue"],
      "candidate_sha": candidate, "source_sha": value["source_sha"],
      "base_sha": value["base_sha"],
      "proposed_version": value["proposed_version"],
      "test_version": checks["integration"]["version"],
      "regression_tag": checks["regression"]["tag"],
      "integration_tag": checks["integration"]["tag"],
      "outcome": "PASS",
    }
    restore_identity(root, remote, attempt)
    identity = _immutable(store, "prelim/identities/" + attempt,
                          identity_payload, writer)
    publish_identity(root, remote, attempt, identity, value["base_sha"])
  fresh()
  return PrelimValidation(
    attempt, candidate, outcome,
    checks["integration"]["version"] if outcome == "PASS" else None,
    audit["revision"],
  )
