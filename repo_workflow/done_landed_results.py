"""Canonical reader projection of verified source-to-landed attestation.

A promoted record is never a synthetic PASS at landedTargetSHA.
The canonical parser can display this separately from source test records.
"""
import json

from .done_evidence_promotion import Promotion, PromotionError
from .test_results_reader import parse_testing_log


def canonical_landed_result(promotion: Promotion) -> dict:
  if not isinstance(promotion, Promotion):
    raise PromotionError("authenticated promotion record required")
  record={
    "testSHA":promotion.tested_source_sha,
    "sourceSHA":promotion.tested_source_sha,
    "landedSHA":promotion.landed_sha,
    "kind":"integration-promotion",
    "result":"promoted",
    "runner":"provider-acceptance",
    "operationId":promotion.operation_id,
    "acceptedCandidateSHA":promotion.accepted_candidate_sha,
    "targetBeforeSHA":promotion.target_before_sha,
    "landedTreeSHA":promotion.landed_tree_sha,
    "sourceTreeSHA":promotion.source_tree_sha,
    "contextDigest":promotion.context_digest,
    "sourceStages":[{
      "stage":stage.stage,
      "sourceSHA":stage.source_sha,
      "runId":stage.provider_run_id,
      "artifactDigest":stage.artifact_digest,
      "status":stage.status,
    } for stage in promotion.stages],
    "disposition":promotion.disposition,
  }
  parsed=parse_testing_log(json.dumps(record,sort_keys=True))
  if len(parsed)!=1 or parsed[0]!=record:
    raise PromotionError("canonical source-to-landed projection invalid")
  return record


def read_landed_results(*, landed_sha: str, read_promotion):
  """Read append-only provider promotions; never extrapolate a PASS."""
  if not callable(read_promotion):
    raise PromotionError("independent promotion reader required")
  try:
    records=read_promotion(landed_sha)
  except Exception as error:
    raise PromotionError("canonical landed evidence UNKNOWN") from error
  if type(records) is not tuple:
    raise PromotionError("provider landed promotions invalid")
  observed=set()
  output=[]
  for result in records:
    if (not isinstance(result,Promotion)
        or result.landed_sha!=landed_sha
        or result.operation_id in observed):
      raise PromotionError("foreign or duplicate landed promotion")
    observed.add(result.operation_id)
    output.append(canonical_landed_result(result))
  return tuple(output)
