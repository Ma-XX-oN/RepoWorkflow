"""Reusable GREEN/temporary PASS eligibility from local canonical evidence.

A provider-backed record cannot be accepted solely because its committed JSON
claims GitHub provenance. Hosted reuse needs independently verified authority.
"""
from __future__ import annotations

import json
from pathlib import Path
import platform
from typing import Callable


def reusable_local_group_passes(
  path: Path, *, stage: str, revision: str, fingerprint: str,
  verify_hosted: Callable[[dict], bool] | None = None,
  raw: str | None = None,
) -> set[str]:
  if raw is None:
    if not path.exists():
      return set()
    try:
      raw = path.read_text(encoding="utf-8")
    except OSError:
      return set()
  latest: dict[str, bool] = {}
  try:
    for line in raw.splitlines():
      record = json.loads(line)
      if not isinstance(record, dict):
        return set()
      if (
        record.get("kind") != stage
        or record.get("testSHA") != revision
        or record.get("catalogueSHA256") != fingerprint
      ):
        continue
      groups = record.get("groups")
      if not isinstance(groups, list) or not groups:
        return set()
      valid = (
        record.get("result") == "succeeded"
        and record.get("reusable") is True
        and record.get("uncommittedChanges") == []
        and record.get("headChangedDuringTest") is False
        and record.get("platform") == {
          "os": platform.system(), "architecture": platform.machine(),
          "runtime": platform.python_version(),
        }
        and (
          record.get("runner") == "local"
          or (
            record.get("runner") == "github-actions"
            and verify_hosted is not None
            and verify_hosted(record)
          )
        )
      )
      for group in groups:
        if (
          not isinstance(group, dict)
          or not isinstance(group.get("group"), str)
        ):
          return set()
        latest[group["group"]] = valid and group.get("exit_code") == 0
  except (ValueError, TypeError):
    return set()
  return {group for group, passed in latest.items() if passed}
