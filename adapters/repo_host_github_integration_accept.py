"""Atomic destination acceptance primitive, never an executor or approval issuer.

An independently authorized, already-certified INT-ATTEMPT may be integrated
only against the exact provider-observed old destination ref SHA. The caller
must independently certify tested source, current allow-policy and review.
A failed/ambiguous push is UNKNOWN; never forge an integration PASS.
"""
import re
import subprocess

from adapters.repo_host_github_integration_lease import (
  _remote_scope, read_lease,
)
from adapters.repo_host_github_integration_destination import (
  read_destination_snapshot,
)


class AcceptanceProviderError(RuntimeError):
  """Provider destination acceptance was refused or remains UNKNOWN."""


_SHA=re.compile(r"[0-9a-f]{40}\Z")
_GUID=re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
_DEST=re.compile(r"[A-Za-z0-9._/-]+\Z")
_ID=re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
_FIELDS={
  "repository","destination","int_attempt_ref","accepted_sha",
  "expected_destination_sha","proposed_sha","guid","lease_generation",
  "holder","authorization_ref","evidence_ref","operation_id",
}


def _validate(request, repository):
  if (type(request) is not dict or set(request)!={"schema_version",
      "repository","operation","request_id","parameters"}
      or request["operation"]!="destination.accept"
      or request["repository"]!=repository):
    raise AcceptanceProviderError("invalid acceptance request envelope")
  record=request["parameters"].get("record")
  if type(record) is not dict or set(record)!=_FIELDS:
    raise AcceptanceProviderError("invalid destination acceptance schema")
  dest=record["destination"]
  guid=record["guid"]
  if (record["repository"]!=repository
      or type(dest) is not str or not _DEST.fullmatch(dest)
      or any(p in ("",".","..") for p in dest.split("/"))
      or type(guid) is not str or not _GUID.fullmatch(guid)
      or type(record["lease_generation"]) is not int
      or record["lease_generation"]<1
      or type(record["holder"]) is not str
      or not record["holder"].strip()):
    raise AcceptanceProviderError("destination claim identity invalid")
  for key in ("accepted_sha","expected_destination_sha","proposed_sha"):
    value=record[key]
    if type(value) is not str or not _SHA.fullmatch(value):
      raise AcceptanceProviderError("SHA identity invalid")
  if (record["expected_destination_sha"]==record["proposed_sha"]
      or type(record["int_attempt_ref"]) is not str
      or not re.fullmatch(
        r"refs/heads/INT-ATTEMPT-[A-Za-z0-9._-]+/"
        +re.escape(dest)+r"-"+re.escape(guid),
        record["int_attempt_ref"])):
    raise AcceptanceProviderError("attempt/destination reference mismatch")
  if (type(record["operation_id"]) is not str
      or not _ID.fullmatch(record["operation_id"])
      or record["operation_id"]!=request["request_id"]):
    raise AcceptanceProviderError("provider operation identity mismatch")
  for key in ("evidence_ref","authorization_ref"):
    if type(record[key]) is not str or not record[key].strip():
      raise AcceptanceProviderError("independent evidence identity absent")
  return record


def _git(root, *args):
  try:
    return subprocess.run(["git","-C",str(root),*args],
      capture_output=True,text=True,check=False,timeout=45)
  except (OSError,subprocess.TimeoutExpired) as error:
    raise AcceptanceProviderError("Git acceptance transport UNKNOWN") from error


def _sha(backend, ref):
  try:
    value=backend.get("git/ref/"+ref.removeprefix("refs/"))
  except Exception as error:
    raise AcceptanceProviderError("provider ref read UNKNOWN") from error
  if (type(value) is not dict or value.get("ref")!=ref
      or type(value.get("object")) is not dict
      or value["object"].get("type")!="commit"):
    raise AcceptanceProviderError("provider ref response untrusted")
  sha=value["object"].get("sha")
  if type(sha) is not str or not _SHA.fullmatch(sha):
    raise AcceptanceProviderError("provider commit identity invalid")
  return sha


def accept_destination(backend, request, root, remote, *, verify_evidence):
  """Apply exact provider CAS only with an independently checked grant.

  Distinct request operation IDs are NOT proof of authorization. The verifier
  must authenticate #104/#542 current testing/approval/admission evidence.
  """
  record=_validate(request,backend.repository)
  if (not callable(verify_evidence)
      or verify_evidence(record) is not True):
    raise AcceptanceProviderError("independent acceptance evidence denied")
  dest=record["destination"]
  before=record["expected_destination_sha"]
  proposed=record["proposed_sha"]
  lease=read_lease(backend,dest)
  if lease!={"destination":dest,"generation":record["lease_generation"],
             "holder":record["holder"],"guid":record["guid"]}:
    raise AcceptanceProviderError("destination lease no longer authoritative")
  snapshot=read_destination_snapshot(backend,dest)
  if snapshot["sha"]!=before:
    raise AcceptanceProviderError("current destination differs; replan")
  if _sha(backend,record["int_attempt_ref"])!=record["accepted_sha"]:
    raise AcceptanceProviderError("certified attempt source changed")
  endpoint=_remote_scope(root,remote,backend)
  if _git(root,"cat-file","-e",proposed+"^{commit}").returncode:
    raise AcceptanceProviderError("proposed landed commit unavailable")
  if _git(root,"merge-base","--is-ancestor",before,proposed).returncode:
    raise AcceptanceProviderError("proposed landed commit is not descendant")
  # A direct compare-and-swap at the provider transport, not a GET+merge.
  target="refs/heads/"+dest
  result=_git(root,"push","--porcelain",
    "--force-with-lease="+target+":"+before,
    endpoint,proposed+":"+target)
  observed=_sha(backend,target)
  if result.returncode:
    # Even observed==proposed is not independently attributable to this
    # operation without the later immutable integration terminal record.
    raise AcceptanceProviderError("destination CAS failed or outcome UNKNOWN")
  if observed!=proposed:
    raise AcceptanceProviderError("destination acceptance readback UNKNOWN")
  if read_lease(backend,dest)!=lease:
    raise AcceptanceProviderError("lease changed during acceptance; reconcile")
  return "applied",{
    "destination":dest,"expected_sha":before,
    "landed_sha":proposed,"operation_id":record["operation_id"],
  }
