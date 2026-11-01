"""Consumer integration: authorized environment verification plus registered suites.

The consumer's configured validation adapter is authoritative for its required
environments. An engine-only platform probe is never a consumer substitute.
"""
from __future__ import annotations

import json
from pathlib import Path

from .git import head_sha
from .test_catalogue import stage_groups
from .test_results_reader import TestCommandError


def run_consumer_integration(
  root: Path, *, engine_root: Path, run_groups, verify, verifier,
  manual_check, publish, get_version,
) -> int:
  root = root.resolve()
  if root == engine_root.resolve():
    raise AssertionError("consumer adapter must not replace engine integration")
  if not (root / ".ci" / "repoworkflow.json").is_file():
    raise TestCommandError(
      "consumer integration requires an authoritative environment adapter"
    )
  groups = stage_groups(root, "integration")
  catalogue = json.loads((root / ".ci" / "tests.json").read_text(encoding="utf-8"))
  if not any(
    isinstance(spec, dict) and spec.get("type") == "integration"
    and spec.get("lifecycle") != "RED"
    and name in groups
    for declaration in catalogue["tests"]
    for name, spec in declaration.items()
    if name not in {"test-harness", "command"}
  ):
    raise TestCommandError("consumer integration requires registered integration tests")

  prepared: list[tuple[str, str]] = []
  outcome = verify(root, engine_root, prepared, verifier)
  if outcome != "PASS":
    return {"FAIL": 1, "INCOMPLETE": 2}[outcome]
  candidate = head_sha(root)
  result = run_groups(root, "integration", groups)
  if result != 0:
    return result
  path = root / ".repoworkflow" / "validation" / (
    "testResults-" + _issue(root) + ".jsonl"
  )
  try:
    record = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
  except (OSError, ValueError, IndexError) as error:
    raise TestCommandError("consumer integration evidence unavailable") from error
  if (
    record.get("kind") != "integration"
    or record.get("testSHA") != candidate
    or record.get("result") != "succeeded"
    or record.get("reusable") is not True
    or head_sha(root) != candidate
    or [item.get("group") for item in record.get("groups", [])] != list(groups)
  ):
    raise TestCommandError("consumer integration evidence is not reusable")
  if manual_check(root) != 0:
    return 2
  version = get_version(root)
  if not isinstance(version, str) or not version.strip():
    raise TestCommandError("consumer integration version is unavailable")
  terminal = dict(record)
  terminal["testVersion"] = version
  terminal["sourceSHA"] = candidate
  with path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(terminal, sort_keys=True) + "\n")
  publish(root, stage="integration")
  return 0


def _issue(root: Path) -> str:
  import re
  from .git import current_branch
  match = re.fullmatch(r"issue-([1-9][0-9]*)(?:-.*)?", current_branch(root))
  if match is None:
    raise TestCommandError("consumer integration requires current issue branch")
  return match.group(1)
