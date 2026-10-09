"""Exact-candidate canonical integration evidence preflight.

Read-only local check; server still must authenticate issuer and enforce tip
freshness atomically before merge.
"""
from __future__ import annotations

import json
from pathlib import Path
import re


class CanonicalEvidenceError(ValueError):
  pass


def require_integration_evidence(
  log: Path, *, candidate: str, required_platforms: tuple[str, ...],
) -> None:
  if not required_platforms or any(
    not isinstance(name, str) or not name for name in required_platforms
  ):
    raise CanonicalEvidenceError("required integration platforms unspecified")
  if re.fullmatch(r"[0-9a-f]{40}", candidate) is None:
    raise CanonicalEvidenceError("invalid candidate SHA")
  try:
    lines = log.read_text(encoding="utf-8").splitlines()
  except OSError as error:
    raise CanonicalEvidenceError("canonical testing log unavailable") from error
  if not lines:
    raise CanonicalEvidenceError("canonical testing log is empty")
  latest: dict[str, bool] = {}
  for line in lines:
    try:
      record = json.loads(line)
    except (ValueError, TypeError) as error:
      raise CanonicalEvidenceError("malformed canonical testing record") from error
    if not isinstance(record, dict):
      raise CanonicalEvidenceError("canonical record is not an object")
    if record.get("kind") != "integration":
      continue
    if record.get("testSHA") != candidate:
      continue
    platform = record.get("platform")
    if not isinstance(platform, dict) or not isinstance(platform.get("os"), str):
      raise CanonicalEvidenceError("integration evidence lacks platform")
    os_name = platform["os"]
    if os_name not in required_platforms:
      continue
    if record.get("runner") not in ("local", "github-actions"):
      raise CanonicalEvidenceError("unrecognised integration result publisher")
    valid = (
      record.get("result") == "succeeded"
      and record.get("reusable") is True
      and record.get("uncommittedChanges") == []
      and record.get("headChangedDuringTest") is False
    )
    if record.get("runner") == "github-actions":
      valid = valid and (
        isinstance(record.get("providerRunId"), int)
        and not isinstance(record.get("providerRunId"), bool)
        and record["providerRunId"] > 0
        and record.get("providerCandidateSHA") == candidate
        and re.fullmatch(
          r"[0-9a-f]{40}", str(record.get("providerInvocationSHA", "")),
        ) is not None
        and record.get("providerStage") == "integration-testing"
      )
    latest[os_name] = valid
  missing = [os_name for os_name in required_platforms if not latest.get(os_name)]
  if missing:
    raise CanonicalEvidenceError(
      "missing or invalid current integration PASS for " + ", ".join(missing)
    )
