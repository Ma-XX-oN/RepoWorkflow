"""Parse remote PRELIM refs into immutable READY integration submissions.

Provider-neutral discovery only: this module never updates refs, orders
integration writes, or turns branch existence into merge authorization.
"""
from dataclasses import dataclass
import re
from uuid import NAMESPACE_URL, uuid5
from collections.abc import Mapping

from .ticket_admission import TicketAdmissionError, policy_path
from .version_adapter import DEVELOPMENT_VERSION_RE


class PrelimQueueError(ValueError):
  """A reserved PRELIM ref or its immutable identity is invalid."""


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_VERSION = re.compile(r"issue-([1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
_PREFIX = "refs/heads/PRELIM-"


def prelim_ref_for_version(version: str) -> str:
  """Name a submission using the issue suffix of its development version.

  Parameters
  ----------
  version : str
      Full repository development version.

  Returns
  -------
  str
      PRELIM-issue-N.generation.iteration Git branch ref.
  """
  match = DEVELOPMENT_VERSION_RE.fullmatch(version) if isinstance(version, str) else None
  if match is None:
    raise PrelimQueueError("PRELIM requires a repository development version")
  return _PREFIX + "issue-" + ".".join(match.groups()[3:])


@dataclass(frozen=True)
class ReadyPrelim:
  ref: str
  sha: str
  umbrella: str
  destination: str
  version: str

  @property
  def guid(self):
    """Return the deterministic correlation key required by provider protocol v2.

    Returns
    -------
    str
        Transport correlation UUID derived from version identity. It is not
        stored in the branch name and never determines submission order.
    """
    return str(uuid5(NAMESPACE_URL, "rwf:prelim:" + self.version))

  @property
  def version_order(self):
    """Return the repository's numeric generation/iteration ordering.

    Returns
    -------
    tuple of int
        Version components after the issue number.
    """
    match = _VERSION.fullmatch(self.version)
    if match is None:
      raise PrelimQueueError("invalid PRELIM version")
    return int(match.group(2)), int(match.group(3))


def parse_ready_prelim(ref: str, sha: str, *, destination: str = "") -> ReadyPrelim | None:
  """Parse version identity; destination comes from authoritative metadata.

  Parameters
  ----------
  ref, sha : str
      Exact provider branch ref and commit.
  destination : str
      Independently resolved parent branch, when available.

  Returns
  -------
  ReadyPrelim or None
      Parsed submission, or None for an unrelated ref.
  """
  if not isinstance(ref, str) or not isinstance(sha, str):
    raise PrelimQueueError("remote ref and SHA must be strings")
  if not ref.startswith(_PREFIX):
    return None
  if _SHA.fullmatch(sha) is None:
    raise PrelimQueueError("PRELIM ref has invalid SHA")
  if not isinstance(destination, str):
    raise PrelimQueueError("PRELIM destination metadata must be a branch name")
  version = ref[len(_PREFIX):]
  match = _VERSION.fullmatch(version)
  if match is None:
    raise PrelimQueueError("PRELIM must be named PRELIM-issue-N.generation.iteration")
  if destination:
    try:
      policy_path(destination)
    except TicketAdmissionError as error:
      raise PrelimQueueError("PRELIM destination is invalid") from error
  return ReadyPrelim(ref, sha, "issue-" + match.group(1), destination, version)


def discover_ready_prelims(remote_refs: Mapping[str, str]) -> tuple[ReadyPrelim, ...]:
  """Parse physical inventory without granting merge authority.

  Parameters
  ----------
  remote_refs : Mapping[str, str]
      Exact provider ref inventory.

  Returns
  -------
  tuple of ReadyPrelim
      All versioned submissions in deterministic display order.
  """
  if not isinstance(remote_refs, Mapping):
    raise PrelimQueueError("remote refs must be a mapping")
  submissions = [parse_ready_prelim(ref, sha) for ref, sha in remote_refs.items()]
  return tuple(sorted((item for item in submissions if item is not None),
                      key=lambda item: (item.umbrella, item.version_order)))


def latest_prelims(submissions):
  """Select the highest numeric version of each issue before reading outcomes.

  Parameters
  ----------
  submissions : iterable of ReadyPrelim
      Physical versioned submissions.

  Returns
  -------
  tuple of ReadyPrelim
      Latest version per issue. Failure cannot cause an older fallback.
  """
  latest = {}
  for item in submissions:
    prior = latest.get(item.umbrella)
    if prior is None or item.version_order > prior.version_order:
      latest[item.umbrella] = item
    elif item.version_order == prior.version_order and item != prior:
      raise PrelimQueueError("one version identifies conflicting PRELIM submissions")
  return tuple(latest.values())


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


def classify_prelims(submissions, *, current_parent_sha, bases):
  """Classify latest versions against the independently observed parent tip.

  Parameters
  ----------
  submissions : iterable of ReadyPrelim
      Physical versioned submissions.
  current_parent_sha : str
      Authoritative parent tip.
  bases : Mapping[str, str]
      Verified parent SHA for each selected latest version. Older versions
      are ignored and require no provenance reads.

  Returns
  -------
  tuple of PrelimPosition
      Current, stale or superseded positions in input order.
  """
  if not isinstance(current_parent_sha, str) or _SHA.fullmatch(current_parent_sha) is None:
    raise PrelimQueueError("authoritative parent SHA required")
  submissions = tuple(submissions)
  latest = {item.ref for item in latest_prelims(submissions)}
  result = []
  for item in submissions:
    if item.ref not in latest:
      result.append(PrelimPosition(item, "superseded", ""))
      continue
    base = bases.get(item.ref)
    if not isinstance(base, str) or _SHA.fullmatch(base) is None:
      raise PrelimQueueError("latest PRELIM parent identity missing")
    result.append(PrelimPosition(item, "current" if base == current_parent_sha else "stale", base))
  return tuple(result)
