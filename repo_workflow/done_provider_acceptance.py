"""Bind #109's guarded executor to #681's provider-neutral v2 CAS operation.

This adapter prepares one exact request. It does not create a PRELIM,
authorize a reviewer, attest test PASS, or certify the landed tree.
"""
from dataclasses import dataclass
import re

from .done_executor import AcceptedIntegration, DoneExecutionError


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_GUID = re.compile(
  r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z"
)
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


@dataclass(frozen=True)
class DestinationAcceptanceFacts:
  repository: str
  ticket: int
  destination: str
  guid: str
  lease_generation: int
  holder: str
  proposed_landed_sha: str


def bind_v2_destination_accept(host, facts: DestinationAcceptanceFacts):
  """Return an execute_certified_done integration callback.

  host must be the trusted #681 IntegrationHost instance, backed by the
  authenticated provider and external verifiers. A receipt is not a
  substitute for the executor's subsequent independent landing readback.
  """
  if not isinstance(facts, DestinationAcceptanceFacts):
    raise DoneExecutionError("destination acceptance facts missing")
  if (not isinstance(facts.repository, str)
      or _REPO.fullmatch(facts.repository) is None
      or type(facts.ticket) is not int or facts.ticket <= 0
      or not isinstance(facts.destination, str)
      or not facts.destination or facts.destination.startswith("/")
      or any(p in ("", ".", "..") for p in facts.destination.split("/"))
      or not isinstance(facts.guid, str)
      or _GUID.fullmatch(facts.guid) is None
      or type(facts.lease_generation) is not int
      or facts.lease_generation < 1
      or not isinstance(facts.holder, str)
      or not facts.holder.strip()
      or not isinstance(facts.proposed_landed_sha, str)
      or _SHA.fullmatch(facts.proposed_landed_sha) is None):
    raise DoneExecutionError("invalid destination acceptance facts")
  if (getattr(host, "repository", None) != facts.repository
      or not callable(getattr(host, "request", None))):
    raise DoneExecutionError("authenticated v2 host binding missing")

  expected_ref = (
    f"refs/heads/INT-ATTEMPT-issue-{facts.ticket}/"
    f"{facts.destination}-{facts.guid}"
  )

  def integrate(int_ref, accepted_sha, destination, old_sha,
                evidence_ref, authorization_ref, operation_id):
    if (int_ref != expected_ref or destination != facts.destination
        or type(accepted_sha) is not str
        or _SHA.fullmatch(accepted_sha) is None
        or type(old_sha) is not str or _SHA.fullmatch(old_sha) is None
        or old_sha == facts.proposed_landed_sha
        or type(operation_id) is not str or not operation_id.strip()
        or type(evidence_ref) is not str or not evidence_ref.strip()
        or type(authorization_ref) is not str
        or not authorization_ref.strip()):
      raise DoneExecutionError("exact v2 destination request identity differs")
    record = {
      "repository": facts.repository,
      "destination": destination,
      "int_attempt_ref": int_ref,
      "accepted_sha": accepted_sha,
      "expected_destination_sha": old_sha,
      "proposed_sha": facts.proposed_landed_sha,
      "guid": facts.guid,
      "lease_generation": facts.lease_generation,
      "holder": facts.holder,
      "authorization_ref": authorization_ref,
      "evidence_ref": evidence_ref,
      "operation_id": operation_id,
    }
    receipt = host.request("destination.accept", operation_id,
                           {"record": record})
    if (type(receipt) is not dict
        or set(receipt) != {
          "destination", "expected_sha", "landed_sha", "operation_id"}
        or receipt["destination"] != destination
        or receipt["expected_sha"] != old_sha
        or receipt["landed_sha"] != facts.proposed_landed_sha
        or receipt["operation_id"] != operation_id):
      raise DoneExecutionError("provider v2 destination receipt differs")
    return AcceptedIntegration(receipt["landed_sha"], True, operation_id)

  return integrate
