"""Persist a source-bound v2 integrated terminal after provider landing.

No local terminal Boolean or successful PR review is accepted as landing.
Provider v2 independently authenticates the external evidence reference.
"""
from dataclasses import dataclass
import re

from .done_executor import AcceptedIntegration
from .prelim_queue import ReadyPrelim


_SHA = re.compile(r"[0-9a-f]{40}\Z")


class TerminalPublicationError(RuntimeError):
  """Authenticated provider terminal identity is not independently readable."""


@dataclass(frozen=True)
class IntegratedTerminal:
  guid: str
  repository: str
  destination: str
  accepted_sha: str
  landed_sha: str
  integration_id: str
  operation_id: str
  terminal_evidence_ref: str
  record: dict


def publish_integrated_terminal(
    *, host, ready: ReadyPrelim, int_attempt_ref,
    accepted_sha, old_destination_sha, landed_sha, operation_id,
    integration_id, terminal_evidence_ref, record_request_id,
    accepted_integration,
):
  """Append exactly once after provider-confirmed destination CAS."""
  if not isinstance(ready, ReadyPrelim):
    raise TerminalPublicationError("authenticated original PRELIM required")
  expected_ref = ready.ref.replace("refs/heads/PRELIM-",
                                   "refs/heads/INT-ATTEMPT-", 1)
  if int_attempt_ref != expected_ref:
    raise TerminalPublicationError("terminal INT attempt GUID/scope differs")
  if any(type(v) is not str or _SHA.fullmatch(v) is None
         for v in (ready.sha, accepted_sha, old_destination_sha, landed_sha)):
    raise TerminalPublicationError("invalid accepted or landed SHA")
  if any(type(v) is not str or not v.strip() for v in (
      operation_id, integration_id, terminal_evidence_ref,
      record_request_id)):
    raise TerminalPublicationError("missing immutable terminal provenance")
  if (not isinstance(accepted_integration, AcceptedIntegration)
      or accepted_integration.verified is not True
      or accepted_integration.landed_sha != landed_sha
      or accepted_integration.operation_id != operation_id):
    raise TerminalPublicationError("independently verified CAS receipt required")
  repository = getattr(host, "repository", None)
  if (not isinstance(repository, str)
      or not callable(getattr(host, "request", None))):
    raise TerminalPublicationError("certified provider v2 host required")

  snapshot = host.request("destination.read",
                          record_request_id + "-before-read", {
                            "destination": ready.destination})
  if (type(snapshot) is not dict
      or snapshot.get("ref") != "refs/heads/" + ready.destination
      or snapshot.get("sha") != landed_sha):
    raise TerminalPublicationError("landing is not current provider tip")
  record = {
    "repository": repository,
    "guid": ready.guid,
    "status": "integrated",
    "prelim_ref": ready.ref,
    "prelim_sha": ready.sha,
    "int_attempt_ref": int_attempt_ref,
    "accepted_sha": accepted_sha,
    "destination_ref": "refs/heads/" + ready.destination,
    "expected_destination_sha": old_destination_sha,
    "observed_destination_sha": landed_sha,
    "landed_sha": landed_sha,
    "integration_id": integration_id,
    "provider_operation_id": operation_id,
    "umbrella": ready.umbrella,
    "terminal_evidence_ref": terminal_evidence_ref,
  }
  try:
    reply = host.request("attempt.record", record_request_id, {
      "guid": ready.guid, "record": record})
    if (type(reply) is not dict or reply != {
        "guid": ready.guid, "record": record}):
      raise TerminalPublicationError("provider terminal publication differs")
  except Exception:
    # Publication result is UNKNOWN; only exact durable provider readback
    # allows promotion to verified integration, never another blind POST.
    pass
  observed = host.request("attempt.read",
                          record_request_id + "-terminal-read", {
                            "guid": ready.guid})
  if (type(observed) is not dict or observed != {
      "guid": ready.guid, "record": record}):
    raise TerminalPublicationError(
      "terminal record missing, foreign or UNKNOWN after publication")
  return IntegratedTerminal(
    ready.guid, repository, ready.destination, accepted_sha, landed_sha,
    integration_id, operation_id, terminal_evidence_ref, record)
