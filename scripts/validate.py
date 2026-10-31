#!/usr/bin/env python3
"""Authoritative catalogue-bound broad self-regression for RepoWorkflow."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from repo_workflow.relationship_store import RelationshipStore, RelationshipStoreError
from repo_workflow.test_catalogue import load_test_catalogue

_MODULE = re.compile(r"^tests\.test_[a-zA-Z0-9_]+$")


def catalogued_modules(root: Path) -> tuple[str, ...]:
  """Require exact coverage of every regression test file by the catalogue."""
  load_test_catalogue(root)
  value = json.loads((root / ".ci/tests.json").read_text(encoding="utf-8"))
  modules = set()
  for declaration in value["tests"]:
    if declaration["test-harness"] != "unittest":
      continue
    for group, entry in declaration.items():
      if group in {"test-harness", "command"}:
        continue
      name = entry["name"]
      if not _MODULE.fullmatch(name):
        raise ValueError(f"invalid unittest catalogue target in {group}: {name}")
      modules.add(name)
  expected = {
    "tests." + path.stem
    for path in (root / "tests").glob("test_*.py")
    if path.is_file()
  }
  if modules != expected:
    raise ValueError(
      "regression catalogue/file mismatch; unregistered="
      + repr(sorted(expected - modules))
      + "; missing source=" + repr(sorted(modules - expected))
    )
  return tuple(sorted(modules))


def _unique_tests(suite: unittest.TestSuite) -> unittest.TestSuite:
  """Run each exact TestCase identity once, including imported aliases."""
  selected = unittest.TestSuite()
  seen = set()

  def visit(node):
    for test in node:
      if isinstance(test, unittest.TestSuite):
        visit(test)
        continue
      identity = test.id()
      if identity not in seen:
        seen.add(identity)
        selected.addTest(test)

  visit(suite)
  return selected


def run(*args: str) -> int:
  return subprocess.run([sys.executable, *args], cwd=ROOT, check=False).returncode


def main() -> int:
  try:
    RelationshipStore(ROOT).read()
    modules = catalogued_modules(ROOT)
  except (RelationshipStoreError, OSError, ValueError, KeyError, TypeError) as error:
    print(f"repository test authority invalid: {error}", file=sys.stderr)
    return 1
  compile_rc = run(
    "-m", "compileall", "-q", "repo_workflow", "repo_workflow.py", "helpers", "tests"
  )
  if compile_rc:
    return 1
  loaded = unittest.defaultTestLoader.loadTestsFromNames(modules)
  suite = _unique_tests(loaded)
  if suite.countTestCases() == 0:
    print("regression catalogue selected no tests", file=sys.stderr)
    return 1
  print(f"RWF catalogue regression: {len(modules)} modules, "
        f"{suite.countTestCases()} unique tests", flush=True)
  result = unittest.TextTestRunner(verbosity=2).run(suite)
  return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
  raise SystemExit(main())
