"""Provider-neutral integration request for an immutable PRELIM candidate.

Creating an integration PR is not merging it. The #119 provider adapter owns
all host APIs and mutation idempotency; #102 owns accepted PRELIM identity.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import uuid

from .host_mutation_dispatch import HostMutationError, dispatch_configured
from .prelim_attempt import (
  PrelimError, _remote_ref, _restore_remote_record,
  _trusted_inputs,
)
from .prelim_identity import validate_attempt
from .prelim_publication import _publish, _restore
from .state_store import StateStoreError, durable_store
from .runtime_identity import runtime_writer_identity

SHA = re.compile(r"[0-9a-f]{40}\Z")


class PrelimIntegrationError(RuntimeError):
  """Request creation cannot be treated as verified integration."""


@dataclass(frozen=True)
class IntegrationRequest:
  attempt: str
  candidate_sha: str
  request_id: str
  number: int
  revision: int


def _state(root, remote, attempt, suffix):
  ref = "refs/heads/prelim-integration-" + suffix + "/" + attempt
  key = "prelim/integration-" + suffix + "/" + attempt
  _restore(root, remote, ref, key)
  store = durable_store(root)
  try:
    return store.read(key)
  except StateStoreError as error:
    if "record is missing:" in str(error):
      return None
    raise


def _save(root, remote, attempt, suffix, payload, base):
  ref = "refs/heads/prelim-integration-" + suffix + "/" + attempt
  key = "prelim/integration-" + suffix + "/" + attempt
  store = durable_store(root)
  try:
    prior = _state(root, remote, attempt, suffix)
    if prior is None:
      try:
        prior = store.create(key, payload, runtime_writer_identity())
      except StateStoreError as error:
        if "record already exists:" not in str(error):
          raise
        prior = store.read(key)
    if prior["value"] != payload:
      raise PrelimIntegrationError("integration request identity collision")
    _publish(root, remote, ref, key, suffix + "-" + attempt, prior, base)
    observed = _state(root, remote, attempt, suffix)
    if observed != prior:
      raise PrelimIntegrationError("provider integration state readback differs")
    return prior
  except (StateStoreError, ValueError) as error:
    raise PrelimIntegrationError("cannot persist provider integration state") from error


def request_prelim_integration(
  root: Path, attempt: str, config: dict, *, repository: str,
  title: str, body: str, authorize,
) -> IntegrationRequest:
  """Create/replay one exact-candidate request with durable provider readback.

  authorize is a REQUIRED independently trusted authorization verifier taking
  (operation, repository, attempt, candidate, destination). It must reject
  absent, expired, revoked or out-of-scope approvals. The provider also owns
  its own mutation authorization; local approval never overrides it.
  """
  root = Path(root).resolve()
  try:
    attempt = str(uuid.UUID(attempt))
    if type(repository) is not str or not re.fullmatch(
      r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository
    ):
      raise ValueError("invalid repository")
    if type(title) is not str or not title or type(body) is not str:
      raise ValueError("invalid integration description")
    if not callable(authorize):
      raise ValueError("trusted authorization verifier required")
    remote = config["repository"]["authoritativeRemote"]
    target = config["repository"]["integrationBranch"]
    if target != "main":
      raise ValueError("integration destination must be main")
  except (KeyError, TypeError, ValueError, AttributeError) as error:
    raise PrelimIntegrationError("invalid integration request") from error

  store = durable_store(root)
  try:
    attempt_record = _restore_remote_record(root, remote, store, attempt)
    if attempt_record is None:
      raise PrelimIntegrationError("authoritative PRELIM attempt missing")
    value = attempt_record["value"]
    validate_attempt(value)
    if value["state"] != "ready" or value["attempt"] != attempt:
      raise PrelimIntegrationError("PRELIM candidate is not ready")
    # A provider-backed PASS from #102, not a caller-supplied GREEN flag.
    accepted = None
  except (PrelimError, StateStoreError, ValueError) as error:
    raise PrelimIntegrationError("unverifiable PRELIM candidate") from error
  # The #102 identity ref has a distinct published naming convention.
  # Never create an integration request by inventing an accepted identity.
  if accepted is None:
    from .prelim_publication import restore_identity
    try:
      restore_identity(root, remote, attempt)
      accepted = store.read("prelim/identities/" + attempt)
    except (StateStoreError, ValueError) as error:
      raise PrelimIntegrationError("accepted PRELIM identity missing") from error
  identity = accepted["value"]
  candidate = value["candidate_sha"]
  if (identity.get("outcome") != "PASS"
      or identity.get("attempt") != attempt
      or identity.get("candidate_sha") != candidate
      or identity.get("source_sha") != value["source_sha"]
      or identity.get("base_sha") != value["base_sha"]
      or identity.get("issue") != value["issue"]):
    raise PrelimIntegrationError("accepted PRELIM identity mismatch")
  branch = "refs/heads/" + value["branch"]

  def fresh():
    _trusted_inputs(
      root, remote, value["issue"], value["source_ref"],
      value["source_sha"], value["base_sha"],
      value["lifecycle_revision"],
    )
    if _remote_ref(root, remote, branch) != candidate:
      raise PrelimIntegrationError("physical PRELIM candidate changed")
    if _remote_ref(root, remote, "refs/heads/main") != value["base_sha"]:
      raise PrelimIntegrationError("integration destination moved")

  fresh()
  if authorize("pull_request.create", repository, attempt,
               candidate, value["base_sha"]) is not True:
    raise PrelimIntegrationError("integration authorization denied")
  # The ID is deterministically bound to the immutable candidate identity.
  request_id = "prelim-" + attempt
  intent = {
    "attempt": attempt, "issue": value["issue"],
    "repository": repository, "source_ref": branch,
    "destination_ref": "refs/heads/main",
    "candidate_sha": candidate, "base_sha": value["base_sha"],
    "identity_revision": accepted["revision"],
    "request_id": request_id, "title": title, "body": body,
  }
  previous = _state(root, remote, attempt, "intent")
  if previous is not None and previous["value"] != intent:
    raise PrelimIntegrationError("stale or changed integration intent")
  result = _state(root, remote, attempt, "result")
  if result is not None:
    if result["value"].get("intent") != intent:
      raise PrelimIntegrationError("different candidate cannot reuse PR")
    recorded = result["value"]["provider"]
    fresh()
    return IntegrationRequest(
      attempt, candidate, request_id, recorded["number"], result["revision"],
    )
  _save(root, remote, attempt, "intent", intent, value["base_sha"])
  fresh()
  request = {
    "schema_version": 1, "operation": "pull_request.create",
    "repository": repository, "request_id": request_id,
    "parameters": {
      "source_ref": branch, "target_ref": "refs/heads/main",
      "expected_source_sha": candidate, "title": title,
      "body": body, "draft": True,
    },
  }
  try:
    response = dispatch_configured(root, request)
    provider = response["result"]
    if provider["number"] == int(value["issue"]):
      raise PrelimIntegrationError("integration request is task issue")
    fresh()
    saved = _save(root, remote, attempt, "result", {
      "intent": intent, "provider": provider,
      "status": "requested-not-integrated",
    }, value["base_sha"])
  except (HostMutationError, StateStoreError, PrelimError,
          KeyError, TypeError) as error:
    # Retain intent and the exact request ID for safe provider reconciliation.
    # Never report creation success for timeout or uncertain host mutation.
    raise PrelimIntegrationError("integration provider outcome unverified") from error
  return IntegrationRequest(
    attempt, candidate, request_id, provider["number"], saved["revision"],
  )
