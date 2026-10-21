"""#109 durable MIT timeout/deferral using #681's provider-v2 ledger.

A timeout never becomes MIT FAIL or a terminal result. The immutable READY
ref remains pending; release is permitted only after exact remote readback.
"""
from dataclasses import dataclass

from .done_host_coordinator import IntegrationHostCoordinator
from .integration_coordination import (
  DestinationLease, MitDeferredEvent, release_prelim,
)
from .prelim_queue import ReadyPrelim


class MitDeferError(RuntimeError):
  """Missing independent MIT defer evidence must retain the claim."""


@dataclass(frozen=True)
class DurableDeferredMit:
  submission: ReadyPrelim
  event: MitDeferredEvent
  released_generation: int


def defer_mit_with_provider(
    *, host, ready: ReadyPrelim, lease: DestinationLease,
    holder: str, reason: str, evidence_ref: str,
    event_request_id: str, read_request_id: str,
):
  """Write then independently read the MIT event; never blindly retry POST."""
  if (not isinstance(ready, ReadyPrelim)
      or not isinstance(lease, DestinationLease)
      or lease.destination != ready.destination
      or lease.active_guid != ready.guid
      or lease.holder != holder
      or type(lease.generation) is not int or lease.generation < 1
      or reason not in {"timeout", "awaiting-manual"}
      or type(evidence_ref) is not str or not evidence_ref.strip()
      or any(type(r) is not str or not r.strip()
             for r in (event_request_id, read_request_id))
      or event_request_id == read_request_id):
    raise MitDeferError("exact MIT timeout identity or provenance absent")
  provider = IntegrationHostCoordinator(host)
  if provider.read_destination_lease(ready.destination) != lease:
    raise MitDeferError("authoritative destination lease changed")
  if provider.read_attempt_result(ready.guid) is not None:
    raise MitDeferError("existing terminal result forbids MIT defer")
  event = {
    "repository":host.repository,
    "guid":ready.guid,
    "destination":ready.destination,
    "prelim_sha":ready.sha,
    "lease_generation":lease.generation,
    "evidence_ref":evidence_ref,
    "reason":reason,
  }
  try:
    published = host.request("mit.deferred.record",event_request_id,{
      "guid":ready.guid,"destination":ready.destination,"event":event})
    if published != {
        "guid":ready.guid,"destination":ready.destination,"event":event}:
      raise MitDeferError("deferred MIT publication identity differs")
  except Exception:
    # An interrupted provider write may have committed: only readback
    # of the exact authenticated event permits lease release.
    pass
  try:
    observed = host.request("mit.deferred.read",read_request_id,{
      "guid":ready.guid,"destination":ready.destination})
  except Exception as error:
    raise MitDeferError("remote deferred MIT readback UNKNOWN") from error
  if observed != {
      "guid":ready.guid,"destination":ready.destination,"event":event}:
    raise MitDeferError("durable MIT event absent or foreign")
  verified = provider.read_mit_deferred_event(ready.guid,ready.destination)
  expected = MitDeferredEvent(
    ready.guid,ready.destination,ready.sha,lease.generation,
    evidence_ref,reason)
  if verified != expected:
    raise MitDeferError("independent MIT event changed during publication")
  released = release_prelim(
    provider,lease,holder,terminal_result="deferred-mit",submission=ready)
  return DurableDeferredMit(ready,expected,released.generation)
