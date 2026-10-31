#!/usr/bin/env python3
"""Authoritative RepoWorkflow engine validation using its test catalogue."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from repo_workflow.relationship_store import RelationshipStore, RelationshipStoreError
from repo_workflow.test_catalogue import stage_groups, TestCatalogueError


def run(*args: str) -> int:
  return subprocess.run([sys.executable, *args], cwd=ROOT, check=False).returncode


def selected_modules(root: Path, stage: str) -> tuple[str, ...]:
  """Map selected Rosetta groups to unique unittest modules.

  Integration-only script probes execute through the integration adapter,
  not recursively as unittest modules or a second validation process.
  """
  catalogue = json.loads((root / ".ci/tests.json").read_text(encoding="utf-8"))
  records = {}
  for declaration in catalogue["tests"]:
    for group, item in declaration.items():
      if group in {"test-harness", "command"}:
        continue
      records[group] = (declaration["test-harness"], item["name"])
  selected = stage_groups(root, stage)
  modules = set()
  probes = set()
  for group in selected:
    harness, name = records[group]
    if harness == "unittest":
      if not name.startswith("tests.test_"):
        raise ValueError("invalid registered Python module: " + name)
      modules.add(name)
    elif stage == "integration" and harness == "script-runner":
      probes.add(name)
    else:
      raise ValueError("unhandled retained test harness: " + group)
  if stage == "integration":
    from repo_workflow.test_integration_engine import PROBES
    expected = {"scripts/" + filename for _, filename in PROBES}
    if probes != expected:
      raise ValueError("integration catalogue probes do not match runner")
  if not modules:
    raise ValueError("catalogue selected no unittest modules")
  return tuple(sorted(modules))


def unique_suite(modules: tuple[str, ...]) -> unittest.TestSuite:
  source = unittest.defaultTestLoader.loadTestsFromNames(modules)
  result = unittest.TestSuite()
  seen = set()
  allowed_modules = frozenset(modules)

  def append_once(suite):
    for test in suite:
      if isinstance(test, unittest.TestSuite):
        append_once(test)
      elif test.__class__.__module__ in allowed_modules and test.id() not in seen:
        seen.add(test.id())
        result.addTest(test)

  append_once(source)
  return result


def main(stage: str = "regression") -> int:
  if stage not in {"regression", "integration"}:
    print("invalid RWF validation stage", file=sys.stderr)
    return 1
  try:
    RelationshipStore(ROOT).read()
    modules = selected_modules(ROOT, stage)
  except (RelationshipStoreError, TestCatalogueError, OSError, ValueError,
          KeyError, TypeError) as error:
    print(f"repository test authority invalid: {error}", file=sys.stderr)
    return 1
  if run("-m", "compileall", "-q", "repo_workflow", "repo_workflow.py",
         "helpers", "tests"):
    return 1
  suite = unique_suite(modules)
  if not suite.countTestCases():
    print("empty catalogue-selected RWF validation suite", file=sys.stderr)
    return 1
  print(f"RWF {stage}: {len(modules)} registered modules, "
        f"{suite.countTestCases()} unique cases", flush=True)
  return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
  if len(sys.argv) != 2 or sys.argv[1] not in {"regression", "integration"}:
    raise SystemExit("usage: validate.py regression|integration")
  raise SystemExit(main(sys.argv[1]))
