"""Validate and display canonical local or remote testing results."""

from __future__ import annotations

import json
import math
from pathlib import Path
import re

from .git import current_branch


class TestCommandError(ValueError):
  pass


def _unique_test_log_fields(pairs: list[tuple[str, object]]) -> dict:
  record: dict[str, object] = {}
  for key, value in pairs:
    if key in record:
      raise TestCommandError("duplicate testing log field")
    record[key] = value
  return record


def _reject_nonfinite_test_log_value(value: str) -> None:
  raise TestCommandError("nonfinite testing log value: " + value)


def results(root: Path, *, remote: bool, git_cmd) -> int:
  match = re.match(r"^issue-([0-9]+)(?:-|$)", current_branch(root))
  if match is None:
    raise TestCommandError("results require an issue branch")
  relative = ".repoworkflow/validation/testResults-" + match.group(1) + ".jsonl"
  if remote:
    branch = current_branch(root)
    git_cmd(root, "fetch", "--no-tags", "origin", "refs/heads/" + branch)
    raw = git_cmd(root, "show", "FETCH_HEAD:" + relative)
  else:
    try:
      raw = (root / relative).read_text(encoding="utf-8")
    except OSError as error:
      raise TestCommandError("testing log is unavailable") from error
  if not raw.strip():
    raise TestCommandError("testing log has no recorded results")
  validated = []
  for line in raw.splitlines():
    try:
      record = json.loads(
        line,
        object_pairs_hook=_unique_test_log_fields,
        parse_constant=_reject_nonfinite_test_log_value,
      )
    except json.JSONDecodeError as error:
      raise TestCommandError("invalid testing log record") from error
    if not isinstance(record, dict) or not all(
      field in record for field in ("testSHA", "kind", "result", "runner")
    ):
      raise TestCommandError("incomplete testing log record")
    if (
      not isinstance(record["testSHA"], str)
      or re.fullmatch(r"[0-9a-f]{40}", record["testSHA"]) is None
      or any(
        not isinstance(record[field], str) or not record[field].strip()
        for field in ("kind", "result", "runner")
      )
    ):
      raise TestCommandError("invalid testing log metadata")
    if "groups" in record:
      groups = record["groups"]
      if not isinstance(groups, list):
        raise TestCommandError("invalid testing log groups")
      seen: set[str] = set()
      for item in groups:
        if not isinstance(item, dict):
          raise TestCommandError("invalid testing log groups")
        name = item.get("group")
        if (
          not isinstance(name, str)
          or not name.strip()
          or name in seen
          or type(item.get("exit_code")) is not int
        ):
          raise TestCommandError("invalid testing log groups")
        seen.add(name)
    def ensure_finite(value):
      if isinstance(value, float) and not math.isfinite(value):
        raise TestCommandError("nonfinite testing log value")
      if isinstance(value, dict):
        for nested in value.values():
          ensure_finite(nested)
      elif isinstance(value, list):
        for nested in value:
          ensure_finite(nested)
    ensure_finite(record)
    validated.append(record)
  for record in validated:
    print(json.dumps(record, sort_keys=True))
  return 0


