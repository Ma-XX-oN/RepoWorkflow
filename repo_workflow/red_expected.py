"""Recognize genuine unittest assertion failures for the RED stage.

Only the known Python unittest harness has an accepted classification;
unknown harnesses and infrastructure errors never establish RED.
"""
from __future__ import annotations

import re
import sys


def assertion_failure(command: tuple[str, ...], code: int, stderr: str) -> bool:
  if (
    code != 1 or len(command) < 4
    or command[0] != sys.executable
    or command[1:3] != ("-m", "unittest")
  ):
    return False
  summaries = re.findall(r"(?m)^FAILED \(([^()\n]+)\)$", stderr)
  if len(summaries) != 1:
    return False
  counts: dict[str, int] = {}
  for item in summaries[0].split(", "):
    match = re.fullmatch(r"(failures|errors|skipped|unexpected successes)=(\d+)", item)
    if match is None or match.group(1) in counts:
      return False
    counts[match.group(1)] = int(match.group(2))
  return (
    counts.get("failures", 0) > 0
    and counts.get("errors", 0) == 0
    and counts.get("unexpected successes", 0) == 0
  )
