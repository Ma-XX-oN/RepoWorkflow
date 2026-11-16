"""Independent ART/AIT/release/MIT stage decision for #109 integration.

Stage verdicts are read only from a separately authenticated service at the
exact current-parent source candidate. Client-supplied PASS flags, cached
candidate evidence, MIT timeout and missing manual review do not authorize CAS.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import re

from .done_executor import DoneExecutionError


_SHA = re.compile(r"[0-9a-f]{40}\Z")


class StageCertificationError(DoneExecutionError):
  """Independently authenticated stage evidence is absent or invalid."""


class StageFailed(StageCertificationError):
  """Exact-source ART/AIT/release/MIT failed; requires repair."""

  def __init__(self, stage, receipt):
    super().__init__(stage+" independently certified FAIL")
    self.stage=stage
    self.receipt=receipt


class MitTimedOut(StageCertificationError):
  """Durable MIT timeout must be recorded and resumed, not merged."""

  def __init__(self, evidence_ref):
    super().__init__("MIT TIMEOUT; durable deferred event required")
    self.evidence_ref=evidence_ref


@dataclass(frozen=True)
class VerifiedStage:
  stage: str
  source_sha: str
  parent_sha: str
  status: str
  provider_run_id: str
  evidence_ref: str
  catalogue_digest: str
  config_digest: str
  inputs_digest: str
  expires_at: str
  independently_authenticated: bool


@dataclass(frozen=True)
class VerifiedMitPolicy:
  source_sha: str
  parent_sha: str
  required: bool
  policy_evidence_ref: str
  independently_authenticated: bool


@dataclass(frozen=True)
class CertifiedStages:
  source_sha: str
  parent_sha: str
  stages: tuple[VerifiedStage,...]
  mit_policy: VerifiedMitPolicy


def certify_stages(*, source_sha, parent_sha, read_stage, read_mit_policy):
  """Fail closed on test FAIL, TIMEOUT, UNKNOWN and forged stage identities.

  This function requires a trusted provider/oracle implementation for both
  callbacks. It cannot mint, skip or infer release/mit outcomes.
  """
  if any(type(x) is not str or _SHA.fullmatch(x) is None
         for x in (source_sha,parent_sha)):
    raise StageCertificationError("invalid exact source or parent identity")
  if not callable(read_stage) or not callable(read_mit_policy):
    raise StageCertificationError("independent provider observations required")
  try:
    policy=read_mit_policy(source_sha,parent_sha)
  except Exception as error:
    raise StageCertificationError("MIT requirement readback UNKNOWN") from error
  if (not isinstance(policy,VerifiedMitPolicy)
      or policy.source_sha != source_sha
      or policy.parent_sha != parent_sha
      or type(policy.required) is not bool
      or type(policy.policy_evidence_ref) is not str
      or not policy.policy_evidence_ref.strip()
      or policy.independently_authenticated is not True):
    raise StageCertificationError("unverified current MIT requirement")
  required=("ART","AIT","release")+(
    ("MIT",) if policy.required else ())
  receipts=[]
  expiries=[]
  for stage in required:
    try:
      receipt=read_stage(stage,source_sha,parent_sha)
    except Exception as error:
      raise StageCertificationError(stage+" provider readback UNKNOWN") from error
    if (not isinstance(receipt,VerifiedStage)
        or receipt.stage != stage
        or receipt.source_sha != source_sha
        or receipt.parent_sha != parent_sha
        or receipt.independently_authenticated is not True
        or any(type(getattr(receipt,k)) is not str
               or not getattr(receipt,k).strip()
               for k in (
                 "provider_run_id","evidence_ref","catalogue_digest",
                 "config_digest","inputs_digest","expires_at"))):
      raise StageCertificationError(stage+" provenance cannot be verified")
    try:
      expires=datetime.fromisoformat(
        receipt.expires_at.replace("Z","+00:00"))
      if (not receipt.expires_at.endswith("Z")
          or expires <= datetime.now(timezone.utc)):
        raise StageCertificationError(stage+" evidence expired")
    except (ValueError,TypeError,AttributeError) as error:
      raise StageCertificationError(stage+" expiry malformed") from error
    if receipt.status == "TIMEOUT" and stage == "MIT":
      raise MitTimedOut(receipt.evidence_ref)
    if receipt.status == "FAIL":
      raise StageFailed(stage,receipt)
    if receipt.status != "PASS":
      raise StageCertificationError(stage+" is not independently PASS")
    receipts.append(receipt)
    expiries.append(expires)
  # A certificate is unusable if any receipt expires while later provider
  # stages are being fetched. Recheck the entire set before returning.
  if any(expiry <= datetime.now(timezone.utc) for expiry in expiries):
    raise StageCertificationError("authenticated stage evidence expired during verification")
  if (len({(r.catalogue_digest,r.config_digest,r.inputs_digest)
           for r in receipts}) != 1):
    raise StageCertificationError("material test inputs differ between stages")
  return CertifiedStages(source_sha,parent_sha,tuple(receipts),policy)
