"""Parse remote PRELIM refs into immutable READY integration submissions.

Provider-neutral discovery only: this module never updates refs, orders
integration writes, or turns branch existence into merge authorization.
"""
from dataclasses import dataclass
import re
from collections.abc import Mapping

from .ticket_admission import TicketAdmissionError, policy_path


class PrelimQueueError(ValueError):
  """A reserved PRELIM ref or its immutable identity is invalid."""


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_GUID = re.compile(
  r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
  r"[0-9a-f]{4}-[0-9a-f]{12}\Z"
)
_UMBRELLA = re.compile(r"issue-[1-9][0-9]*\Z")
_PREFIX = "refs/heads/PRELIM-"


@dataclass(frozen=True)
class ReadyPrelim:
  ref: str
  sha: str
  umbrella: str
  destination: str
  guid: str


def parse_ready_prelim(ref: str, sha: str) -> ReadyPrelim | None:
  """Ignore unrelated refs but fail closed for malformed reserved refs."""
  if not isinstance(ref, str) or not isinstance(sha, str):
    raise PrelimQueueError("remote ref and SHA must be strings")
  if not ref.startswith(_PREFIX):
    return None
  if _SHA.fullmatch(sha) is None:
    raise PrelimQueueError("PRELIM ref has invalid SHA")
  remainder = ref[len(_PREFIX):]
  umbrella, separator, suffix = remainder.partition("/")
  if not separator or _UMBRELLA.fullmatch(umbrella) is None:
    raise PrelimQueueError("PRELIM umbrella is invalid")
  if len(suffix) < 38 or suffix[-37] != "-":
    raise PrelimQueueError("PRELIM GUID delimiter is missing")
  destination, guid = suffix[:-37], suffix[-36:]
  if _GUID.fullmatch(guid) is None:
    raise PrelimQueueError("PRELIM GUID is invalid")
  try:
    policy_path(destination)
  except TicketAdmissionError as error:
    raise PrelimQueueError("PRELIM destination is invalid") from error
  return ReadyPrelim(ref, sha, umbrella, destination, guid)


def discover_ready_prelims(remote_refs: Mapping[str, str]) -> tuple[ReadyPrelim, ...]:
  """Return a deterministic inventory, NOT queue priority or merge order."""
  if not isinstance(remote_refs, Mapping):
    raise PrelimQueueError("remote refs must be a mapping")
  seen_guids = set()
  submissions = []
  for ref, sha in remote_refs.items():
    candidate = parse_ready_prelim(ref, sha)
    if candidate is None:
      continue
    if candidate.guid in seen_guids:
      raise PrelimQueueError("duplicate PRELIM attempt GUID")
    seen_guids.add(candidate.guid)
    submissions.append(candidate)
  return tuple(sorted(submissions, key=lambda candidate: candidate.ref))


def verify_immutable_prelims(
    recorded: Mapping[str, str], observed: Mapping[str, str],
    *, terminal_refs: Mapping[str, str] | None = None,
) -> tuple[ReadyPrelim, ...]:
  """Reject moved/deleted previously recorded refs; allow new submissions.

  The caller persists new discovered identities atomically before acting.
  Final hostile-writer enforcement belongs to the deferred provider ruleset.
  """
  if not isinstance(recorded, Mapping) or not isinstance(observed, Mapping):
    raise PrelimQueueError("recorded and observed refs must be mappings")
  ready = discover_ready_prelims(observed)
  # Caller must obtain terminal_refs from independently authenticated durable
  # history; a missing physical ref is not itself proof of successful cleanup.
  terminal_refs = {} if terminal_refs is None else terminal_refs
  if not isinstance(terminal_refs, Mapping):
    raise PrelimQueueError("terminal evidence must be a mapping")
  for ref, original_sha in recorded.items():
    prior = parse_ready_prelim(ref, original_sha)
    if prior is None:
      raise PrelimQueueError("recorded ref is not a PRELIM submission")
    if ref not in observed:
      if terminal_refs.get(ref) == original_sha:
        continue
      raise PrelimQueueError("previously recorded PRELIM ref disappeared")
    if observed[ref] != original_sha:
      raise PrelimQueueError("published PRELIM commit changed")
  return ready


@dataclass(frozen=True)
class PrelimPosition:
  """A submission's current, stale-latest, or superseded position."""

  submission: ReadyPrelim
  position: str
  parent_sha: str


def classify_prelims(submissions, *, current_parent_sha, bases, predecessors):
  """Classify submissions using verified parent and predecessor records.

  Parameters
  ----------
  submissions : tuple[ReadyPrelim, ...]
      Published identities for one destination, including retained history.
  current_parent_sha : str
      Independently observed authoritative destination tip.
  bases : Mapping[str, str]
      Verified parent SHA indexed by PRELIM ref.
  predecessors : Mapping[str, str | None]
      Verified prior PRELIM ref, or None for the first submission.

  Returns
  -------
  tuple[PrelimPosition, ...]
      Positions in inventory order. Failed latest submissions remain latest.

  Raises
  ------
  PrelimQueueError
      Missing, foreign, cyclic or incomparable generation provenance.
  """
  if _SHA.fullmatch(current_parent_sha) is None:
    raise PrelimQueueError("authoritative parent SHA required")
  inventory = {}
  for submission in submissions:
    if not isinstance(submission, ReadyPrelim) or submission.ref in inventory:
      raise PrelimQueueError("unique PRELIM submissions required")
    inventory[submission.ref] = submission
  if len({item.destination for item in inventory.values()}) > 1:
    raise PrelimQueueError("classify one destination at a time")
  superseded = set()
  for ref, item in inventory.items():
    if ref not in bases or not isinstance(bases[ref], str) or not _SHA.fullmatch(bases[ref]):
      raise PrelimQueueError("PRELIM base identity missing")
    if ref not in predecessors:
      raise PrelimQueueError("PRELIM predecessor identity missing")
    seen = {ref}
    prior = predecessors[ref]
    while prior is not None:
      if prior in seen or prior not in inventory:
        raise PrelimQueueError("cyclic or missing PRELIM predecessor")
      older = inventory[prior]
      if older.umbrella != item.umbrella or older.destination != item.destination:
        raise PrelimQueueError("foreign PRELIM predecessor")
      seen.add(prior)
      superseded.add(prior)
      if prior not in predecessors:
        raise PrelimQueueError("PRELIM predecessor identity missing")
      prior = predecessors[prior]
  latest = {}
  for ref, item in inventory.items():
    if ref not in superseded:
      if item.umbrella in latest:
        raise PrelimQueueError("incomparable latest PRELIM submissions")
      latest[item.umbrella] = ref
  return tuple(
    PrelimPosition(item, "superseded" if ref in superseded else
                   "current" if bases[ref] == current_parent_sha else "stale",
                   bases[ref])
    for ref, item in inventory.items()
  )
