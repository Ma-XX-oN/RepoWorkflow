"""Independent GitHub App Checks issuer for #109 release/MIT decisions.

A GitHub Actions regression result cannot stand in for a separate release or
manual-test authority. The trusted host supplies an out-of-band app ID and a
provider API reader. This module can only verify; it cannot issue PASS.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re

from .done_stage_certification import (
  MitTimedOut,StageCertificationError,StageFailed,VerifiedStage,
)


_SHA=re.compile(r"[0-9a-f]{40}\Z")
_STAGE_NAMES={"release":"rwf-done-release","MIT":"rwf-done-manual-test"}


def _repository_valid(value):
  return (type(value) is str
          and re.fullmatch(
            r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",value) is not None
          and all(part not in (".","..") for part in value.split("/")))



class CheckIssuerError(StageCertificationError):
  """Independent issuer identity or provider evidence cannot be proved."""


@dataclass(frozen=True)
class CheckIssuerBinding:
  repository: str
  stage: str
  issue: int
  source_sha: str
  parent_sha: str
  check_run_id: int
  app_id: int
  provider_evidence_ref: str
  catalogue_digest: str
  config_digest: str
  inputs_digest: str
  expires_at: str
  tester_id: str | None = None


def _canonical(payload):
  return json.dumps(payload,sort_keys=True,separators=(",",":"))


def _external_id(binding):
  """Application scope binds issued evidence to tested current-parent SHA."""
  data={
    "schema_version":1,"repository":binding.repository,
    "stage":binding.stage,"issue":binding.issue,
    "source_sha":binding.source_sha,"parent_sha":binding.parent_sha,
    "catalogue_digest":binding.catalogue_digest,
    "config_digest":binding.config_digest,
    "inputs_digest":binding.inputs_digest,
    "provider_evidence_ref":binding.provider_evidence_ref,
    "app_id":binding.app_id,
    "expires_at":binding.expires_at,
    "tester_id":binding.tester_id,
  }
  return "rwf-done-v1-"+hashlib.sha256(
    _canonical(data).encode("utf-8")).hexdigest()


def _check_exact(binding,check,trusted_app_id):
  return (
    type(check) is dict
    and type(check.get("id")) is int
    and check["id"]==binding.check_run_id
    and check.get("name")==_STAGE_NAMES[binding.stage]
    and check.get("head_sha")==binding.source_sha
    and check.get("external_id")==_external_id(binding)
    and check.get("status")=="completed"
    and type(check.get("app")) is dict
    and type(check["app"].get("id")) is int
    and check["app"]["id"]==trusted_app_id==binding.app_id
    and type(check["app"].get("slug")) is str
    and bool(check["app"]["slug"].strip())
    and check["app"]["slug"]!="github-actions"
    and check.get("conclusion") in ("success","failure","timed_out")
  )


def verify_check_stage(*, binding, trusted_app_id, read_check):
  """Observe a distinct authenticated issuer twice; never mint an approval."""
  if (not isinstance(binding,CheckIssuerBinding)
      or type(binding.stage) is not str
      or binding.stage not in _STAGE_NAMES
      or type(binding.issue) is not int or binding.issue<=0
      or not _repository_valid(binding.repository)
      or any(type(x) is not str or _SHA.fullmatch(x) is None
             for x in (binding.source_sha,binding.parent_sha))
      or type(binding.check_run_id) is not int or binding.check_run_id<=0
      or type(trusted_app_id) is not int or trusted_app_id<=0
      or type(binding.app_id) is not int or binding.app_id!=trusted_app_id
      or (binding.stage=="MIT"
          and (type(binding.tester_id) is not str
               or not binding.tester_id.strip()))
      or (binding.stage=="release" and binding.tester_id is not None)
      or any(type(x) is not str or not x.strip()
             for x in (
               binding.provider_evidence_ref,binding.catalogue_digest,
               binding.config_digest,binding.inputs_digest,binding.expires_at))
      or not callable(read_check)):
    raise CheckIssuerError("independent release/MIT issuer binding required")
  # A cryptographically bound expiration is still unusable once elapsed.
  # Check locally before querying and again after the independent reread.
  def valid_expiry():
    if not binding.expires_at.endswith("Z"):
      return False
    try:
      expiration=datetime.fromisoformat(
        binding.expires_at.replace("Z","+00:00"))
      return expiration.tzinfo is not None and (
        expiration > datetime.now(timezone.utc))
    except (TypeError,ValueError,OverflowError):
      return False
  if not valid_expiry():
    raise CheckIssuerError("independent release/MIT check expired or invalid")
  try:
    before=read_check(binding.repository,binding.check_run_id)
    if not _check_exact(binding,before,trusted_app_id):
      raise CheckIssuerError("foreign or incomplete GitHub App check authority")
    after=read_check(binding.repository,binding.check_run_id)
  except CheckIssuerError:
    raise
  except Exception as error:
    raise CheckIssuerError("GitHub App stage provider read UNKNOWN") from error
  if before!=after or not _check_exact(binding,after,trusted_app_id):
    raise CheckIssuerError("GitHub App issuer status changed during verification")
  if not valid_expiry():
    raise CheckIssuerError("independent release/MIT check expired during readback")
  evidence=VerifiedStage(
    binding.stage,binding.source_sha,binding.parent_sha,
    {"success":"PASS","failure":"FAIL","timed_out":"TIMEOUT"}[
      before["conclusion"]],
    str(binding.check_run_id),binding.provider_evidence_ref,
    binding.catalogue_digest,binding.config_digest,
    binding.inputs_digest,binding.expires_at,True)
  if evidence.status=="FAIL":
    raise StageFailed(binding.stage,evidence)
  if evidence.status=="TIMEOUT":
    if binding.stage=="MIT":
      raise MitTimedOut(binding.provider_evidence_ref)
    raise CheckIssuerError("release provider timed out; no PASS")
  return evidence


def read_github_check(repository, check_run_id):
  """Use the actual GitHub Checks API, not an in-memory stage assertion."""
  from .github_evidence import github_json
  if (not _repository_valid(repository)
      or type(check_run_id) is not int or check_run_id<=0):
    raise CheckIssuerError("invalid authenticated provider check locator")
  return github_json(
    "https://api.github.com/repos/"+repository+
    "/check-runs/"+str(check_run_id))


def bind_github_check_oracle(*, binding, trusted_app_id,
                             read_check=read_github_check):
  """Create the release/MIT stage reader with an explicit trusted app ID."""
  if not isinstance(binding,CheckIssuerBinding):
    raise CheckIssuerError("exact independent provider binding required")

  def stage_for(source_sha,parent_sha):
    if (source_sha!=binding.source_sha
        or parent_sha!=binding.parent_sha):
      raise CheckIssuerError(
        "current source/parent differs from independent issuer binding")
    return verify_check_stage(
      binding=binding,trusted_app_id=trusted_app_id,
      read_check=read_check)

  return stage_for
