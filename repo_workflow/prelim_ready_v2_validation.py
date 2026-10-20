"""#102-authenticated validation for new destination-qualified PRELIM builds.

Local candidate preparation never publishes READY. Only independent hosted
regression and integration PASS, with immutable exact-source tags, can create
the provider-backed v2 acceptance identity for subsequent READY publication.
"""
from pathlib import Path
import tempfile
import uuid

from .git import git
from .prelim_ready_v2_tags import expected_v2_terminal_tags
from .prelim_attempt import _local_ref, _trusted_inputs
from .prelim_publication import _publish, _restore
from .prelim_ready_v2_record import (
  preparation_key, preparation_ref, prepared_snapshot,
)
from .prelim_validation import (
  HostedObservation, PrelimValidationError, _immutable, _observation,
)
from .runtime_identity import runtime_writer_identity
from .state_store import durable_store
from .terminal_tag import _remote_target
from .version_adapter import read_version


def v2_identity_key(guid):
  return "prelim/v2-identities/" + guid


def v2_identity_ref(guid):
  return "refs/heads/prelim-v2-identity-state/" + guid


def validate_destination_prelim(
    root: Path, guid: str, config: dict, *, regression: HostedObservation,
    integration: HostedObservation,
):
  """Persist immutable PASS identity only for the exact physical candidate."""
  root = Path(root).resolve()
  try:
    guid = str(uuid.UUID(guid))
  except (ValueError, TypeError, AttributeError) as error:
    raise PrelimValidationError("invalid destination candidate GUID") from error
  store = durable_store(root)
  candidate_record = store.read(preparation_key(guid))
  value = candidate_record["value"]
  candidate = prepared_snapshot(value)
  remote = config["repository"]["authoritativeRemote"]

  def fresh():
    _trusted_inputs(
      root, remote, candidate.issue, value["source_ref"],
      candidate.source_sha, candidate.base_sha,
      value["lifecycle_revision"], require_current_base=False,
    )
    if _local_ref(root, preparation_ref(guid)) != candidate.candidate_sha:
      raise PrelimValidationError("local physical PRELIM candidate changed")
    for sha in (candidate.source_sha, candidate.base_sha):
      if git(root, "merge-base", "--is-ancestor",
             sha, candidate.candidate_sha, check=False).returncode:
        raise PrelimValidationError("prepared candidate ancestry changed")
  fresh()
  with tempfile.TemporaryDirectory(prefix="rwf-qualified-version-") as tmp:
    workspace = Path(tmp) / "candidate"
    git(root, "worktree", "add", "--detach", str(workspace),
        candidate.candidate_sha)
    try:
      if read_version(workspace, config) != candidate.proposed_version:
        raise PrelimValidationError("physical candidate version changed")
    finally:
      git(root, "worktree", "remove", "--force", str(workspace))
  checks = {
    "regression": _observation("regression", candidate.candidate_sha,
                               regression),
    "integration": _observation("integration", candidate.candidate_sha,
                                integration),
  }
  if any(item["outcome"] != "PASS" for item in checks.values()):
    raise PrelimValidationError("qualified candidate has no complete PASS")
  versions = {item["version"] for item in checks.values()}
  if len(versions) != 1:
    raise PrelimValidationError("candidate terminal versions disagree")
  version = next(iter(versions))
  try:
    required_tags = expected_v2_terminal_tags(version, candidate.issue)
  except ValueError as error:
    raise PrelimValidationError("candidate terminal version invalid") from error
  for stage, item in checks.items():
    if item["tag"] != required_tags[stage]:
      raise PrelimValidationError("candidate terminal tag has wrong phase")
    if _remote_target(root, remote, item["tag"]) != candidate.candidate_sha:
      raise PrelimValidationError("immutable candidate terminal tag differs")
  fresh()
  payload = {
    "kind": "destination-qualified-v2", "attempt": guid,
    "issue": candidate.issue, "destination": candidate.destination,
    "source_sha": candidate.source_sha, "base_sha": candidate.base_sha,
    "candidate_sha": candidate.candidate_sha,
    "proposed_version": candidate.proposed_version,
    "test_version": next(iter(versions)),
    "regression_tag": checks["regression"]["tag"],
    "integration_tag": checks["integration"]["tag"],
    "outcome": "PASS",
  }
  key = v2_identity_key(guid)
  ref = v2_identity_ref(guid)
  _restore(root, remote, ref, key)
  record = _immutable(store, key, payload, runtime_writer_identity())
  _publish(root, remote, ref, key, "v2-identity-" + guid,
           record, candidate.base_sha)
  fresh()
  return record
