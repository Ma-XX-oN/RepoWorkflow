"""Adapt certified #681 IntegrationHost to #109's coordinator protocol.

All writes remain provider v2 operations. Local state is not a lock, a
queue or an authority for successful integration.
"""
from hashlib import sha256
from uuid import uuid4

from .integration_coordination import (
  CoordinationError, DestinationLease, MitDeferredEvent,
  MitResumeAuthorization,
)
from .prelim_queue import discover_ready_prelims


def _request_id(kind: str, *parts) -> str:
  material = "\0".join(str(part) for part in parts)
  return kind + "-" + sha256(material.encode("utf-8")).hexdigest()


class IntegrationHostCoordinator:
  def __init__(self, host):
    if (not isinstance(getattr(host, "repository", None), str)
        or not callable(getattr(host, "request", None))):
      raise CoordinationError("certified v2 integration host is required")
    self.host = host

  def _read(self, operation, params):
    # Read-only requests must not reuse an idempotency-cache key. Any
    # lifecycle or lease transition must be observable on the next read.
    request_id = _request_id(
      operation.replace(".", "-"), self.host.repository,
      *params.values(), uuid4().hex)
    try:
      return self.host.request(operation, request_id, params)
    except Exception as error:
      raise CoordinationError(f"provider {operation} UNKNOWN") from error

  def read_ready_prelims(self):
    result = self._read("refs.list", {"prefix": "refs/heads/PRELIM-"})
    if type(result) is not dict or set(result) != {"refs"}:
      raise CoordinationError("remote PRELIM inventory unverified")
    return discover_ready_prelims(result["refs"])

  def read_destination_lease(self, destination):
    result = self._read("lease.read", {"destination": destination})
    if (type(result) is not dict
        or set(result) != {"destination", "generation", "guid", "holder"}
        or result["destination"] != destination
        or type(result["generation"]) is not int
        or result["generation"] < 0):
      raise CoordinationError("destination lease readback is invalid")
    return DestinationLease(destination, result["generation"],
                            result["guid"], result["holder"])

  def compare_and_set_destination_lease(self, before, after):
    if (not isinstance(before, DestinationLease)
        or not isinstance(after, DestinationLease)
        or before.destination != after.destination
        or after.generation != before.generation + 1):
      raise CoordinationError("lease CAS transition is invalid")
    params = {
      "destination": before.destination,
      "expected_generation": before.generation,
      "expected_holder": before.holder,
      "expected_guid": before.active_guid,
      "holder": after.holder,
      "guid": after.active_guid,
    }
    request_id = _request_id(
      "lease-cas", self.host.repository, *params.values())
    failed=None
    try:
      result = self.host.request("lease.cas", request_id, params)
    except Exception as error:
      failed=error
      result=None
    if failed is None and (type(result) is not dict or result != {
          "destination": after.destination,
          "generation": after.generation,
          "guid": after.active_guid,
          "holder": after.holder,
        }):
      raise CoordinationError("destination lease CAS response differs")
    # The write can commit before the response is lost. A fresh independent
    # provider read (never a reused idempotency key) is the only authority.
    try:
      observed=self.read_destination_lease(after.destination)
    except Exception as error:
      raise CoordinationError("destination lease CAS readback UNKNOWN") from error
    if observed != after:
      raise CoordinationError("destination lease CAS outcome UNKNOWN; readback differs") from failed
    return True

  def read_attempt_result(self, guid):
    result = self._read("attempt.read", {"guid": guid})
    if type(result) is not dict or result.get("guid") != guid:
      raise CoordinationError("provider attempt record unverified")
    record = result.get("record")
    if record is None:
      return None
    if (type(record) is not dict or record.get("guid") != guid
        or record.get("repository") != self.host.repository
        or record.get("status") not in {"integrated", "failed", "rejected"}):
      raise CoordinationError("provider terminal record unverified")
    return record["status"]

  def read_mit_deferred_event(self, guid, destination):
    result = self._read(
      "mit.deferred.read", {"guid": guid, "destination": destination})
    if (type(result) is not dict or result.get("guid") != guid
        or result.get("destination") != destination):
      raise CoordinationError("MIT deferred result unverified")
    event = result.get("event")
    if event is None:
      return None
    if (type(event) is not dict
        or event.get("repository") != self.host.repository
        or event.get("guid") != guid
        or event.get("destination") != destination):
      raise CoordinationError("MIT defer provenance unverified")
    return MitDeferredEvent(
      event["guid"], event["destination"], event["prelim_sha"],
      event["lease_generation"], event["evidence_ref"], event["reason"])

  def read_mit_resume_authorization(self, guid, destination):
    result = self._read(
      "mit.resume.read", {"guid": guid, "destination": destination})
    if (type(result) is not dict or result.get("guid") != guid
        or result.get("destination") != destination):
      raise CoordinationError("MIT approval result unverified")
    approval = result.get("authorization")
    if approval is None:
      return None
    if (type(approval) is not dict
        or approval.get("repository") != self.host.repository
        or approval.get("guid") != guid
        or approval.get("destination") != destination):
      raise CoordinationError("MIT approval provenance unverified")
    return MitResumeAuthorization(
      approval["guid"], approval["destination"], approval["prelim_sha"],
      approval["expected_generation"], approval["deferred_evidence_ref"],
      approval["evidence_ref"], approval["approved"])
