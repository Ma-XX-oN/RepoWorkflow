"""Probe process argument limits used by future rwf-test batching.

This deliberately invokes subprocesses without a shell because RepoWorkflow will
pass argv arrays directly to the platform process API.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


PAYLOAD_BYTES = 512
MAX_PROBE_BYTES = 4 * 1024 * 1024


def _argv_for(payload_bytes: int) -> list[str]:
  count, remainder = divmod(payload_bytes, PAYLOAD_BYTES)
  args = ["x" * PAYLOAD_BYTES] * count
  if remainder:
    args.append("x" * remainder)
  return [sys.executable, "-c", "pass", *args]


def _launches(payload_bytes: int) -> bool:
  try:
    subprocess.run(
      _argv_for(payload_bytes),
      check=True,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
    )
    return True
  except (OSError, subprocess.CalledProcessError):
    return False


def _maximum_payload() -> int:
  low = 0
  high = 1024
  while high < MAX_PROBE_BYTES and _launches(high):
    low = high
    high *= 2
  high = min(high, MAX_PROBE_BYTES)
  if _launches(high):
    return high

  while low + 1 < high:
    middle = (low + high) // 2
    if _launches(middle):
      low = middle
    else:
      high = middle
  return low


def _environment_size() -> int:
  if os.name == "nt":
    # CreateProcessW receives a UTF-16 environment block with NUL after each
    # entry and an additional final NUL.
    entries = [f"{key}={value}" for key, value in os.environ.items()]
    return sum(len(entry.encode("utf-16-le")) + 2 for entry in entries) + 2

  return sum(
    len(os.fsencode(key)) + 1 + len(os.fsencode(value)) + 1
    for key, value in os.environ.items()
  )


def main() -> int:
  arg_max = None
  if hasattr(os, "sysconf") and "SC_ARG_MAX" in os.sysconf_names:
    arg_max = os.sysconf("SC_ARG_MAX")

  maximum = _maximum_payload()
  report = {
    "platform": sys.platform,
    "os_name": os.name,
    "arg_max": arg_max,
    "environment_bytes": _environment_size(),
    "probe_argument_payload_bytes": maximum,
    "probe_next_byte_launches": _launches(maximum + 1),
    "python": sys.version.split()[0],
  }
  print(json.dumps(report, indent=2, sort_keys=True))

  # The probe must actually find a boundary below its artificial ceiling.
  if maximum >= MAX_PROBE_BYTES:
    print("probe ceiling reached before process limit", file=sys.stderr)
    return 1
  if report["probe_next_byte_launches"]:
    print("binary-search boundary was not stable", file=sys.stderr)
    return 1
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
