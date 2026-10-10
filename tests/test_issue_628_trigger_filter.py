"""Specification tests for the #628 hosted-trigger static gate."""
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
  "issue628_filter", ROOT / "scripts" / "check-ci-trigger-filter.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

GOOD = """name: test
on:
  push:
    branches-ignore:
      - main
      - prelim-main
      - 'prelim-main-*'
    paths:
      - '.ci/run'
permissions:
  contents: read
"""


class TriggerFilterTests(unittest.TestCase):
  def test_exact_marker_only_and_all_three_exclusions_accepted(self):
    value = gate.validate_on_demand(GOOD)
    self.assertEqual(value["paths"], [".ci/run"])
    self.assertIn("prelim-main", value["branches-ignore"])

  def test_missing_exact_prelim_main_exclusion_rejected(self):
    malformed = GOOD.replace("      - prelim-main\n", "")
    with self.assertRaisesRegex(gate.TriggerFilterError, "prelim-main"):
      gate.validate_on_demand(malformed)

  def test_missing_prelim_main_wildcard_rejected(self):
    malformed = GOOD.replace("      - 'prelim-main-*'\n", "")
    with self.assertRaisesRegex(gate.TriggerFilterError, "prelim-main"):
      gate.validate_on_demand(malformed)

  def test_missing_main_exclusion_rejected(self):
    with self.assertRaises(gate.TriggerFilterError):
      gate.validate_on_demand(GOOD.replace("      - main\n", ""))

  def test_source_path_enabled_rejected(self):
    with self.assertRaisesRegex(gate.TriggerFilterError, "only .ci/run"):
      gate.validate_on_demand(
        GOOD.replace("      - '.ci/run'", "      - '.ci/run'\n      - '**'")
      )

  def test_pull_request_trigger_rejected(self):
    with self.assertRaisesRegex(gate.TriggerFilterError, "unrequested"):
      gate.validate_on_demand(
        GOOD.replace("  push:", "  pull_request:\n  push:")
      )

  def test_workflow_dispatch_trigger_rejected(self):
    with self.assertRaises(gate.TriggerFilterError):
      gate.validate_on_demand(
        GOOD.replace("  push:", "  workflow_dispatch:\n  push:")
      )

  def test_unknown_event_trigger_rejected(self):
    with self.assertRaisesRegex(gate.TriggerFilterError, "unrequested"):
      gate.validate_on_demand(
        GOOD.replace("  push:", "  release:\n  push:")
      )

  def test_unrecognised_extra_push_filter_rejected(self):
    with self.assertRaisesRegex(gate.TriggerFilterError, "additional"):
      gate.validate_on_demand(
        GOOD.replace("    paths:", "    paths-ignore:\n      - 'README.md'\n    paths:")
      )

  def test_missing_path_filter_rejected(self):
    with self.assertRaises(gate.TriggerFilterError):
      gate.validate_on_demand(
        GOOD.replace("    paths:\n      - '.ci/run'\n", "")
      )

  def test_missing_push_rejected(self):
    with self.assertRaises(gate.TriggerFilterError):
      gate.validate_on_demand(GOOD.replace("  push:", "  issue_comment:"))

  def test_multiple_unapproved_paths_rejected(self):
    with self.assertRaises(gate.TriggerFilterError):
      gate.validate_on_demand(
        GOOD.replace("      - '.ci/run'", "      - 'source.txt'")
      )


if __name__ == "__main__":
  unittest.main()
