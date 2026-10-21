"""Stateless, destination-scoped READY scheduling over provider inventory.

No queue file, branch, timestamp ordering or GUID-as-priority is invented.
Selection authority is a separately authenticated coordinator decision.
"""
from dataclasses import dataclass

from .done_host_coordinator import IntegrationHostCoordinator
from .prelim_queue import ReadyPrelim


class ReadySelectionError(RuntimeError):
  """A destination candidate was not independently selected."""


@dataclass(frozen=True)
class DestinationInventory:
  destination: str
  ready: tuple[ReadyPrelim, ...]
  selected: ReadyPrelim | None


def select_ready_for_destination(
    *, host, destination, select_authorized,
):
  """Read current physical PRELIMs and authorize one exact READY identity."""
  if (type(destination) is not str or not destination.strip()
      or not callable(select_authorized)):
    raise ReadySelectionError("valid destination and selector required")
  provider=IntegrationHostCoordinator(host)
  submissions=tuple(
    ready for ready in provider.read_ready_prelims()
    if ready.destination==destination)
  if not submissions:
    return DestinationInventory(destination,(),None)
  # Multiple umbrellas may share one destination. The authoritative
  # coordinator alone determines order; sorted ref order is not priority.
  try:
    chosen=select_authorized(destination,submissions)
  except Exception as error:
    raise ReadySelectionError("provider scheduling authority UNKNOWN") from error
  if (not isinstance(chosen,ReadyPrelim)
      or chosen not in submissions
      or chosen.destination != destination):
    raise ReadySelectionError("unverified selected READY or destination")
  current=tuple(
    ready for ready in provider.read_ready_prelims()
    if ready.destination==destination)
  if chosen not in current:
    raise ReadySelectionError("selected immutable READY changed")
  return DestinationInventory(destination,current,chosen)
