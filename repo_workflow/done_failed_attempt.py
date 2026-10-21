"""Durable failed terminal: no successful integration or invented retry.

The caller must supply independent provider-verified failed-stage evidence.
This preserves the immutable submission's identity after lease release.
"""
from dataclasses import dataclass

from .done_host_coordinator import IntegrationHostCoordinator
from .integration_coordination import DestinationLease, release_prelim
from .prelim_queue import ReadyPrelim


class FailureRecordError(RuntimeError):
  """Exact failed attempt cannot be authenticated or persisted."""


@dataclass(frozen=True)
class FailedIntegrationEvidence:
  guid: str
  accepted_sha: str
  expected_parent_sha: str
  observed_parent_sha: str
  integration_id: str
  operation_id: str
  evidence_ref: str
  authenticated: bool


def record_failed_attempt(*, host, ready: ReadyPrelim,
                          lease: DestinationLease, holder: str,
                          evidence: FailedIntegrationEvidence,
                          terminal_request_id: str, read_request_id: str):
  """Write immutable failed status, read it back and release exact lease."""
  if (not isinstance(ready, ReadyPrelim)
      or not isinstance(lease, DestinationLease)
      or lease.active_guid != ready.guid
      or lease.destination != ready.destination or lease.holder != holder
      or not isinstance(evidence, FailedIntegrationEvidence)
      or evidence.guid != ready.guid or evidence.authenticated is not True
      or not isinstance(terminal_request_id, str)
      or not terminal_request_id.strip()
      or not isinstance(read_request_id, str) or not read_request_id.strip()
      or read_request_id == terminal_request_id):
    raise FailureRecordError("independent failed-attempt identity required")
  provider=IntegrationHostCoordinator(host)
  if provider.read_destination_lease(ready.destination) != lease:
    raise FailureRecordError("destination lease changed before failed terminal")
  try:
    previous = provider.read_attempt_result(ready.guid)
  except Exception as error:
    raise FailureRecordError("prior terminal record unverified") from error
  if previous is not None:
    raise FailureRecordError("a prior terminal result already exists")
  record={
    "repository":host.repository,
    "guid":ready.guid,
    "status":"failed",
    "prelim_ref":ready.ref,
    "prelim_sha":ready.sha,
    "int_attempt_ref":ready.ref.replace(
      "refs/heads/PRELIM-","refs/heads/INT-ATTEMPT-",1),
    "accepted_sha":evidence.accepted_sha,
    "destination_ref":"refs/heads/"+ready.destination,
    "expected_destination_sha":evidence.expected_parent_sha,
    "observed_destination_sha":evidence.observed_parent_sha,
    "landed_sha":None,
    "integration_id":evidence.integration_id,
    "provider_operation_id":evidence.operation_id,
    "umbrella":ready.umbrella,
    "terminal_evidence_ref":evidence.evidence_ref,
  }
  try:
    host.request("attempt.record",terminal_request_id,{
      "guid":ready.guid,"record":record})
  except Exception:
    pass  # Reconcile exact provider record; never retry a blind append.
  try:
    observed=host.request("attempt.read",read_request_id,{"guid":ready.guid})
  except Exception as error:
    raise FailureRecordError("failed terminal readback UNKNOWN") from error
  if observed != {"guid":ready.guid,"record":record}:
    raise FailureRecordError("failed terminal missing or mismatched")
  released=release_prelim(
    provider,lease,holder,terminal_result="failed")
  return record,released
