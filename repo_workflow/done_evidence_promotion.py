"""Append-only evidence promotion after independently verified destination CAS.

A promotion records provenance, not a claim that hosted tests ran on the
landed SHA. Source evidence must be authenticated by a separate verifier.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import re


_SHA = re.compile(r"[0-9a-f]{40}\Z")


class PromotionError(RuntimeError):
  """Provider landing or exact-source evidence cannot be authenticated."""


@dataclass(frozen=True)
class AuthenticatedStage:
  stage: str
  source_sha: str
  provider_run_id: str
  artifact_digest: str
  catalogue_digest: str
  config_digest: str
  inputs_digest: str
  expires_at: str
  status: str
  authenticated: bool


@dataclass(frozen=True)
class Promotion:
  operation_id: str
  tested_source_sha: str
  accepted_candidate_sha: str
  target_before_sha: str
  landed_sha: str
  landed_tree_sha: str
  source_tree_sha: str
  context_digest: str
  stages: tuple[AuthenticatedStage, ...]
  disposition: str = "source-tested-accepted-at-destination"


def make_promotion(*, operation_id, tested_source_sha, accepted_candidate_sha,
                   target_before_sha, landed_sha, landed_tree_sha,
                   source_tree_sha, context_digest, stages,
                   independently_verified_landing, equivalent_test_inputs,
                   as_of_utc):
  """Require complete authenticated source-stage facts, no inferred PASS."""
  sha_values = (
    tested_source_sha, accepted_candidate_sha, target_before_sha,
    landed_sha, landed_tree_sha, source_tree_sha)
  if any(type(v) is not str or _SHA.fullmatch(v) is None
         for v in sha_values):
    raise PromotionError("invalid tested, landed or tree identity")
  if (type(operation_id) is not str or not operation_id.strip()
      or type(context_digest) is not str or not context_digest.strip()):
    raise PromotionError("missing operation or integration-context identity")
  if (independently_verified_landing is not True
      or equivalent_test_inputs is not True
      or landed_tree_sha != source_tree_sha):
    raise PromotionError("landed provenance and test inputs not equivalent")
  if (type(stages) is not tuple or len(stages) != 3
      or {s.stage for s in stages if isinstance(s, AuthenticatedStage)}
         != {"regression", "integration", "release"}):
    raise PromotionError("complete independent release and integration stages required")
  if (not isinstance(as_of_utc, datetime)
      or as_of_utc.tzinfo is None
      or as_of_utc.utcoffset() is None):
    raise PromotionError("verified UTC evaluation time required")
  now = as_of_utc.astimezone(timezone.utc)
  for stage in stages:
    if (not isinstance(stage, AuthenticatedStage)
        or stage.source_sha != tested_source_sha
        or stage.status != "PASS"
        or stage.authenticated is not True
        or any(type(getattr(stage, key)) is not str
               or not getattr(stage, key).strip()
               for key in (
                 "provider_run_id", "artifact_digest", "catalogue_digest",
                 "config_digest", "inputs_digest", "expires_at"))):
      raise PromotionError("unauthenticated, incomplete or foreign stage")
    try:
      if (not stage.expires_at.endswith("Z")
          or datetime.fromisoformat(
            stage.expires_at.replace("Z", "+00:00")) <= now):
        raise PromotionError("authenticated stage evidence expired")
    except (ValueError, TypeError, AttributeError) as error:
      raise PromotionError("malformed stage evidence expiry") from error
  if (len({(s.catalogue_digest, s.config_digest, s.inputs_digest)
           for s in stages}) != 1):
    raise PromotionError("stage material inputs are inconsistent")
  return Promotion(
    operation_id, tested_source_sha, accepted_candidate_sha,
    target_before_sha, landed_sha, landed_tree_sha,
    source_tree_sha, context_digest, stages)


def publish_promotion(record: Promotion, *, persist, readback):
  """Publish idempotently and accept only immutable exact-record readback.

  persist/readback are trusted provider adapters. Their remote authorization
  and append-only guarantees are independently tested in the integration lane.
  """
  if not isinstance(record, Promotion):
    raise PromotionError("validated exact provenance required")
  try:
    persist(record)
  except Exception:
    # Lost response: read exact persisted evidence, never retry blindly.
    pass
  try:
    observed = readback(record.operation_id)
  except Exception as error:
    raise PromotionError("promotion provider readback UNKNOWN") from error
  if observed != record or type(observed) is not Promotion:
    raise PromotionError("promotion not persisted at exact operation identity")
  return observed
