#!/usr/bin/env python3
"""Fail-closed evaluation of exact-attempt Self CI release jobs."""
from __future__ import annotations

import sys

PLATFORMS = ("ubuntu-latest", "windows-latest", "macos-latest")
MATRICES = ("Probe argv limits", "Probe graph renderer", "Probe ticket merge")


def release_tier(lines: list[str]) -> str:
  jobs: dict[str, str] = {}
  for line in lines:
    parts = line.rstrip("\n").split("\t")
    if len(parts) != 2 or not parts[0] or parts[1] not in (
      "success", "failure", "cancelled", "skipped", "timed_out",
      "neutral", "action_required",
    ):
      raise ValueError("invalid or incomplete job record")
    name, conclusion = parts
    if name in jobs:
      raise ValueError(f"duplicate CI job: {name}")
    jobs[name] = conclusion

  for name in ("classify", "plan"):
    if jobs.get(name) != "success":
      raise ValueError(f"required job did not succeed: {name}")
  if jobs.get("issue-validate") != "skipped":
    raise ValueError("issue-only validation is not release evidence")

  expected = {
    f"{prefix} ({os_name})"
    for prefix in MATRICES for os_name in PLATFORMS
  }
  matrix = {
    name for name in jobs
    if any(name.startswith(prefix + " (") for prefix in MATRICES)
  }
  if jobs.get("validate") == "success":
    if matrix != expected:
      raise ValueError("integration matrix has missing or unexpected platforms")
    if any(jobs[name] != "success" for name in expected):
      raise ValueError("integration matrix did not fully pass")
    return "integration"

  if jobs.get("validate") == "skipped":
    # GitHub reports one unexpanded placeholder job for a skipped matrix.
    skipped = {f"{prefix} (${{{{ matrix.os }}}})" for prefix in MATRICES}
    if matrix != skipped:
      raise ValueError("docs-only matrix must be entirely skipped")
    if any(jobs[name] != "skipped" for name in skipped):
      raise ValueError("docs-only release has executed integration jobs")
    return "docs"

  raise ValueError("authoritative validation did not succeed")


def main() -> int:
  try:
    tier = release_tier(sys.stdin.readlines())
  except ValueError as error:
    print(f"Release refused: {error}", file=sys.stderr)
    return 1
  print(f"Verified Self CI release tier: {tier}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
