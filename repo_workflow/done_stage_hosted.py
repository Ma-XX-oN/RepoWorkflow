"""Existing GitHub Actions artifact authority for #109 ART and AIT.

The artifact verifier authenticates exactly the hosted candidate, invocation,
run, jobs, and archive. It cannot certify an independent release stage or MIT;
those must be sourced from their own provider and review authority.
"""
from dataclasses import dataclass
import re

from .done_stage_certification import VerifiedStage
from .github_artifact import verify_hosted_record


_SHA=re.compile(r"[0-9a-f]{40}\Z")
_STAGES={"ART":"regression-testing","AIT":"integration-testing"}


class HostedStageError(RuntimeError):
  """The exact stage artifact or parent binding cannot be authenticated."""


@dataclass(frozen=True)
class HostedStageBinding:
  stage: str
  tested_sha: str
  expected_parent_sha: str
  provider_run_id: int
  artifact_digest: str
  catalogue_digest: str
  config_digest: str
  inputs_digest: str
  evidence_ref: str
  expires_at: str
  independently_authenticated: bool


def verified_hosted_automatic_stage(*, repository, stage, tested_sha,
                                    expected_parent_sha,
                                    read_record,read_binding,
                                    verify_artifact=verify_hosted_record):
  """Return exact verified ART/AIT, or reject; no inferred release or MIT."""
  if (stage not in _STAGES
      or type(repository) is not str or "/" not in repository
      or any(type(value) is not str or _SHA.fullmatch(value) is None
             for value in (tested_sha,expected_parent_sha))
      or any(not callable(fn)
             for fn in (read_record,read_binding,verify_artifact))):
    raise HostedStageError("authenticated exact hosted stage request required")
  try:
    record=read_record(stage,tested_sha,expected_parent_sha)
    bound=read_binding(stage,tested_sha,expected_parent_sha)
  except Exception as error:
    raise HostedStageError("hosted run and candidate readback UNKNOWN") from error
  if (type(record) is not dict
      or record.get("testSHA")!=tested_sha
      or record.get("providerCandidateSHA")!=tested_sha
      or record.get("providerStage")!=_STAGES[stage]
      or type(record.get("providerRunId")) is not int
      or not isinstance(bound,HostedStageBinding)
      or bound.stage!=stage
      or bound.tested_sha!=tested_sha
      or bound.expected_parent_sha!=expected_parent_sha
      or bound.provider_run_id!=record["providerRunId"]
      or bound.independently_authenticated is not True
      or any(type(getattr(bound,name)) is not str
             or not getattr(bound,name).strip()
             for name in (
               "artifact_digest","catalogue_digest","config_digest",
               "inputs_digest","evidence_ref","expires_at"))):
    raise HostedStageError("foreign or unverified hosted stage binding")
  try:
    certified=verify_artifact(
      record,repo=repository,stage=_STAGES[stage])
  except Exception as error:
    raise HostedStageError("hosted artifact verifier UNKNOWN") from error
  if certified is not True:
    raise HostedStageError("hosted source artifact not independently PASS")
  # A second provider observation ensures that the stage-source/parent
  # relationship did not change while external evidence was verified.
  try:
    current=read_binding(stage,tested_sha,expected_parent_sha)
  except Exception as error:
    raise HostedStageError("post-stage binding UNKNOWN") from error
  if current!=bound:
    raise HostedStageError("hosted stage binding changed during verification")
  return VerifiedStage(
    stage,tested_sha,expected_parent_sha,"PASS",
    str(bound.provider_run_id),bound.evidence_ref,
    bound.catalogue_digest,bound.config_digest,
    bound.inputs_digest,bound.expires_at,True)
