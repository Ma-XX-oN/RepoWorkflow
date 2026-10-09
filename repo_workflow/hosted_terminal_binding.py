"""Authorize terminal tag inputs from one authenticated hosted observation.

This is a read-only gate. It never invents a development version, tags Git,
or treats a marker/evidence commit as the original tested candidate.
"""
from __future__ import annotations

import json
from pathlib import Path

from .hosted_version_identity import HostedVersionError, resolve_hosted_version


class HostedTerminalError(ValueError):
  pass


def bind_hosted_terminal(
  root: Path, *, stage: str, candidate: str, invocation: str,
  run_id: int, canonical_log: Path,
) -> dict[str, str] | None:
  if stage not in {"regression-testing", "integration-testing"}:
    raise HostedTerminalError("stage is not terminal regression/integration")
  phase = stage.removesuffix("-testing")
  if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
    raise HostedTerminalError("invalid hosted provider run ID")
  try:
    proof = resolve_hosted_version(root, invocation, canonical_log)
  except HostedVersionError as error:
    raise HostedTerminalError("invalid hosted version ancestry/evidence") from error
  if proof["candidate_sha"] != candidate or proof["stage"] != phase:
    raise HostedTerminalError("hosted terminal candidate or stage mismatch")
  version = proof["test_version"]
  if version is None:
    raise HostedTerminalError("no authoritative hosted development version")
  try:
    lines = canonical_log.read_text(encoding="utf-8").splitlines()
    if not lines:
      raise HostedTerminalError("missing canonical hosted result")
    record = json.loads(lines[-1])
  except (OSError, UnicodeError, ValueError) as error:
    raise HostedTerminalError("missing or malformed hosted result") from error
  if not isinstance(record, dict):
    raise HostedTerminalError("hosted result must be an object")
  for name, expected in {
    "runner": "github-actions",
    "kind": phase,
    "testSHA": candidate,
    "providerCandidateSHA": candidate,
    "providerInvocationSHA": invocation,
    "providerRunId": run_id,
    "providerStage": stage,
    "testVersion": version,
  }.items():
    if record.get(name) != expected:
      raise HostedTerminalError("hosted provider evidence mismatch: " + name)
  status = record.get("result")
  if status == "incomplete":
    return None
  if status not in {"succeeded", "failed"}:
    raise HostedTerminalError("hosted result is not a known terminal outcome")
  if (
    record.get("headChangedDuringTest") is not False
    or record.get("uncommittedChanges") != []
    or (status == "succeeded" and record.get("reusable") is not True)
  ):
    raise HostedTerminalError("hosted terminal result lacks clean candidate proof")
  return {
    "stage": phase,
    "version": version,
    "candidate": candidate,
    "outcome": "PASS" if status == "succeeded" else "FAIL",
  }
