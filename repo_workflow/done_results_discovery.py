"""Read-only canonical results discovery for a verified landed SHA.

A landed merge SHA is *not* a tested source SHA. Return the historic test
records unchanged, with a separate immutable promotion relation. Provider
adapters must authenticate promotion, current target and source log readback.
"""
from dataclasses import dataclass
import re

from .done_evidence_promotion import Promotion, AuthenticatedStage
from .test_results_reader import parse_testing_log, TestCommandError


_SHA=re.compile(r"[0-9a-f]{40}\Z")


class LandedResultsError(RuntimeError):
  """Current landing and source-test identity are not independently proven."""


@dataclass(frozen=True)
class LandedResults:
  destination: str
  landed_sha: str
  tested_source_sha: str
  operation_id: str
  relation: str
  original_results: tuple[dict,...]
  evidence: Promotion


def discover_landed_results(*, destination, landed_sha,
                            read_destination, read_promotion,
                            read_source_log):
  """Return verified provenance, never a synthetic PASS at the landed SHA."""
  if (type(destination) is not str or not destination.strip()
      or type(landed_sha) is not str or _SHA.fullmatch(landed_sha) is None
      or any(not callable(fn) for fn in (
        read_destination,read_promotion,read_source_log))):
    raise LandedResultsError("canonical provider readers and SHA required")
  try:
    tip=read_destination(destination)
    relation=read_promotion(destination,landed_sha)
  except Exception as error:
    raise LandedResultsError("canonical landed readback UNKNOWN") from error
  if (type(tip) is not dict or tip.get("destination")!=destination
      or tip.get("sha")!=landed_sha
      or tip.get("independently_authenticated") is not True
      or not isinstance(relation,Promotion)
      or relation.landed_sha!=landed_sha
      or relation.disposition!="source-tested-accepted-at-destination"
      or len(relation.stages)!=3
      or {stage.stage for stage in relation.stages
          if isinstance(stage,AuthenticatedStage)}
         != {"regression","integration","release"}
      or any(not isinstance(stage,AuthenticatedStage)
             or stage.authenticated is not True
             or stage.status!="PASS"
             or stage.source_sha!=relation.tested_source_sha
             for stage in relation.stages)):
    raise LandedResultsError("landed result not authenticated at current tip")
  try:
    source_text=read_source_log(relation.tested_source_sha)
    source_records=parse_testing_log(source_text)
  except (TestCommandError,Exception) as error:
    raise LandedResultsError("canonical original source results UNKNOWN") from error
  if (not source_records or any(
      record.get("testSHA") != relation.tested_source_sha
      for record in source_records)):
    raise LandedResultsError("original test SHA differs from promotion")
  try:
    still_current=read_destination(destination)
    still_promoted=read_promotion(destination,landed_sha)
  except Exception as error:
    raise LandedResultsError("post-discovery provider readback UNKNOWN") from error
  if still_current!=tip or still_promoted!=relation:
    raise LandedResultsError("destination or promotion moved during discovery")
  return LandedResults(
    destination,landed_sha,relation.tested_source_sha,
    relation.operation_id,relation.disposition,tuple(source_records),
    relation)
