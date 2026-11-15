"""Verify the single immutable PRELIM candidate at the integration boundary."""
from dataclasses import dataclass
import re
from uuid import uuid4

from .prelim_queue import ReadyPrelim


_SHA = re.compile(r"[0-9a-f]{40}\Z")


class PrelimCandidateError(RuntimeError):
  """Provider source or destination differs from the certified candidate."""


@dataclass(frozen=True)
class VerifiedPrelimCandidate:
  prelim_ref: str
  prelim_sha: str
  accepted_sha: str
  expected_destination_sha: str


def verify_prelim_candidate(*, host, ready, expected_parent_sha, accepted_sha):
  """Read back one PRELIM without creating or mutating an execution branch.

  Parameters
  ----------
  host : IntegrationHost
      Independently authenticated provider.
  ready : ReadyPrelim
      Exact immutable submission being certified.
  expected_parent_sha, accepted_sha : str
      Parent and source bound to the applicable test evidence.

  Returns
  -------
  VerifiedPrelimCandidate
      Exact provider readback. Reconstruction must publish a new PRELIM
      generation; changing an already submitted candidate is rejected.
  """
  if not isinstance(ready, ReadyPrelim):
    raise PrelimCandidateError("authenticated READY identity required")
  if any(type(value) is not str or _SHA.fullmatch(value) is None
         for value in (ready.sha, expected_parent_sha, accepted_sha)):
    raise PrelimCandidateError("invalid pinned source or destination SHA")
  if accepted_sha != ready.sha:
    raise PrelimCandidateError("changed source requires a new PRELIM generation")
  if not callable(getattr(host, "request", None)):
    raise PrelimCandidateError("authenticated provider required")
  for _ in range(2):
    inventory = host.request("refs.list", "candidate-refs-" + uuid4().hex,
                             {"prefix": "refs/heads/PRELIM-"})
    if (type(inventory) is not dict or type(inventory.get("refs")) is not dict
        or inventory["refs"].get(ready.ref) != ready.sha):
      raise PrelimCandidateError("immutable READY ref changed or disappeared")
    parent = host.request("destination.read", "candidate-parent-" + uuid4().hex,
                          {"destination": ready.destination})
    if (type(parent) is not dict
        or parent.get("ref") != "refs/heads/" + ready.destination
        or parent.get("sha") != expected_parent_sha):
      raise PrelimCandidateError("destination moved during candidate verification")
  return VerifiedPrelimCandidate(ready.ref, ready.sha, accepted_sha, expected_parent_sha)
