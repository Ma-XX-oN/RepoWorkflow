"""Run every registered #545 module together, including unchanged suites."""
import json
from pathlib import Path
import unittest


CATALOGUE = Path(__file__).resolve().parents[1] / ".ci/tests.json"


def load_tests(loader, tests, pattern):
  data = json.loads(CATALOGUE.read_text(encoding="utf-8"))
  names = sorted({
    details["name"]
    for test_group in data["tests"]
    for name, details in test_group.items()
    if name.startswith("issue-545-")
    and name != "issue-545-all-acceptance"
    and isinstance(details, dict)
  })
  suite = unittest.TestSuite()
  for name in names:
    suite.addTests(loader.loadTestsFromName(name))
  return suite
