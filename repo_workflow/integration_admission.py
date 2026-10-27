"""Provider-neutral admission decision for a pinned destination revision.

Inputs must come from authoritative ticket relationships and an exact
destination commit. The executor still rechecks the destination at merge time.
"""
from collections.abc import Callable
from dataclasses import dataclass
import re

from .prelim_queue import ReadyPrelim
from .ticket_admission import TicketAdmissionError, parse_policy, policy_path


class AdmissionError(ValueError):
  """Untrusted or incomplete destination admission facts."""


_SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class AdmissionDecision:
  ticket: int
  destination: str
  destination_sha: str
  allowed: bool
  reason: str


def decide_admission(
    candidate: ReadyPrelim,
    destination_sha: str,
    *,
    resolve_parent: Callable[[int], str],
    read_policy: Callable[[str, str], str | None],
) -> AdmissionDecision:
  """Read the candidate's immediate parent and destination policy at SHA.

  `read_policy` accepts (destination_sha, relative_repo_path), returning
  None only when the file is absent from that exact destination commit.
  The caller must not pass content taken from PRELIM or INT-ATTEMPT.
  """
  if not isinstance(candidate, ReadyPrelim):
    raise AdmissionError("READY PRELIM identity is required")
  if not isinstance(destination_sha, str) or _SHA.fullmatch(destination_sha) is None:
    raise AdmissionError("authoritative destination commit SHA is required")
  ticket = int(candidate.umbrella[len("issue-"):])
  try:
    parent = resolve_parent(ticket)
  except (KeyError, LookupError) as error:
    raise AdmissionError("authoritative parent relationship is unavailable") from error
  if not isinstance(parent, str) or not parent:
    raise AdmissionError("invalid authoritative parent identity")
  if parent != candidate.destination:
    return AdmissionDecision(
      ticket, candidate.destination, destination_sha, False,
      "ticket is not an immediate child of destination",
    )
  relative_path = policy_path(candidate.destination).as_posix()
  content = read_policy(destination_sha, relative_path)
  if content is None:
    return AdmissionDecision(
      ticket, candidate.destination, destination_sha, True,
      "no destination allow-list restriction",
    )
  try:
    allowed = ticket in parse_policy(content)
  except TicketAdmissionError as error:
    raise AdmissionError("invalid destination allow-list") from error
  return AdmissionDecision(
    ticket, candidate.destination, destination_sha, allowed,
    "ticket explicitly admitted" if allowed else "ticket not allow-listed",
  )
