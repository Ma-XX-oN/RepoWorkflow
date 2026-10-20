"""Independent provider-readback adapter for #109 source-to-landed records.

The caller cannot synthesize test PASS or landed equivalence: authenticated
provider stage/landing readers are mandatory. The original source record is
preserved; no release stage can be inferred from a regression suite.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from .done_evidence_promotion import (
  AuthenticatedStage, PromotionError, make_promotion, publish_promotion,
)


@dataclass(frozen=True)
class VerifiedLanding:
  operation_id: str
  tested_source_sha: str
  accepted_candidate_sha: str
  target_before_sha: str
  landed_sha: str
  landed_tree_sha: str
  source_tree_sha: str
  context_digest: str
  independently_verified: bool
  inputs_equivalent: bool


def promote_from_provider(*, operation_id, tested_source_sha,
                          read_landing, read_stage, persist, readback):
  """Publish only source evidence independently rediscovered by provider.

  Each reader must be an independently authenticated provider-bound oracle.
  No supplied PASS booleans, cached stage receipts or user-controlled clock.
  The final canonical results publisher is a separate required integration.
  """
  for name, callback in (
      ("landing", read_landing), ("stage", read_stage),
      ("append", persist), ("readback", readback)):
    if not callable(callback):
      raise PromotionError("independent provider " + name + " required")
  if type(operation_id) is not str or not operation_id.strip():
    raise PromotionError("exact operation identity required")
  try:
    landing = read_landing(operation_id)
  except Exception as error:
    raise PromotionError("landing readback UNKNOWN") from error
  if (not isinstance(landing, VerifiedLanding)
      or landing.operation_id != operation_id
      or landing.tested_source_sha != tested_source_sha):
    raise PromotionError("provider landed source or operation differs")
  expected_stages = ("regression", "integration", "release")
  stages = []
  for stage_name in expected_stages:
    try:
      observed = read_stage(stage_name, tested_source_sha)
    except Exception as error:
      raise PromotionError("hosted stage readback UNKNOWN") from error
    if (not isinstance(observed, AuthenticatedStage)
        or observed.stage != stage_name
        or observed.source_sha != tested_source_sha):
      raise PromotionError("provider returned foreign or absent stage")
    stages.append(observed)
  record = make_promotion(
    operation_id=operation_id,
    tested_source_sha=tested_source_sha,
    accepted_candidate_sha=landing.accepted_candidate_sha,
    target_before_sha=landing.target_before_sha,
    landed_sha=landing.landed_sha,
    landed_tree_sha=landing.landed_tree_sha,
    source_tree_sha=landing.source_tree_sha,
    context_digest=landing.context_digest,
    stages=tuple(stages),
    independently_verified_landing=landing.independently_verified,
    equivalent_test_inputs=landing.inputs_equivalent,
    as_of_utc=datetime.now(timezone.utc),
  )
  outcome = publish_promotion(record, persist=persist, readback=readback)
  # Verification following a lost publication ACK must not reuse stale
  # stage observations. A changed original makes a published promotion
  # unverifiable even when its exact append-only record is still present.
  for previous in stages:
    try:
      current = read_stage(previous.stage, tested_source_sha)
    except Exception as error:
      raise PromotionError("post-publication stage readback UNKNOWN") from error
    if current != previous:
      raise PromotionError("source evidence changed during publication")
  return outcome
