"""Read-only cooperative admission policy for immediate-child integration.

The caller must supply a checkout of the authoritative current destination;
PRELIM or INT-ATTEMPT copies are never policy authorities.
"""

from pathlib import Path, PurePosixPath
import re


class TicketAdmissionError(ValueError):
  """The destination admission policy cannot be interpreted safely."""


def policy_path(destination: str) -> Path:
  """Compute the destination-scoped policy path without escaping its root."""
  if not isinstance(destination, str) or not destination:
    raise TicketAdmissionError("destination branch is required")
  path = PurePosixPath(destination)
  if (path.is_absolute() or any(part in (".", "..") for part in
      destination.split("/")) or any(not part for part in
      destination.split("/")) or "\\" in destination):
    raise TicketAdmissionError("unsafe destination branch name")
  if any(not re.fullmatch(r"[A-Za-z0-9._-]+", part)
      for part in destination.split("/")):
    raise TicketAdmissionError("invalid destination branch name")
  return Path(".repoworkflow") / "allow-tickets" / ("to-" + destination)


def parse_policy(contents: str) -> frozenset[int]:
  """Read one strictly formatted positive decimal issue number per line."""
  if not isinstance(contents, str):
    raise TicketAdmissionError("policy contents must be text")
  if contents == "":
    return frozenset()
  entries = contents.splitlines()
  if not entries:
    return frozenset()
  numbers = set()
  for index, line in enumerate(entries, 1):
    if re.fullmatch(r"[1-9][0-9]*", line) is None:
      raise TicketAdmissionError(f"invalid policy issue on line {index}")
    number = int(line)
    if number in numbers:
      raise TicketAdmissionError(f"duplicate policy issue on line {index}")
    numbers.add(number)
  return frozenset(numbers)


def ticket_allowed(destination_root: Path, destination: str,
    ticket: int, *, immediate_child: bool) -> bool:
  """Apply only the current destination's optional admission restriction.

  Caller independently proves immediate-child membership from authoritative
  ticket relationships. This function never grants descendant inheritance.
  """
  if type(ticket) is not int or ticket <= 0:
    raise TicketAdmissionError("ticket must be a positive integer")
  if type(immediate_child) is not bool:
    raise TicketAdmissionError("immediate_child must be a boolean")
  if not immediate_child:
    return False
  path = Path(destination_root) / policy_path(destination)
  try:
    content = path.read_text(encoding="utf-8")
  except FileNotFoundError:
    if path.parent.is_dir() and not path.exists():
      return True
    if not path.parent.exists():
      return True
    raise
  except UnicodeError as error:
    raise TicketAdmissionError("invalid policy text encoding") from error
  return ticket in parse_policy(content)
