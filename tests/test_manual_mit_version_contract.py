"""Independent required Q/R version contract probes for RWF #703.

These are deliberate RED acceptance tests against unresolved #109 adapters.
A real repair must make all three ordinary assertions PASS.
"""
import tempfile
from pathlib import Path
import unittest

from repo_workflow.engine_version_adapter import (
  _TASK, transition_engine_version,
)
from repo_workflow.version_adapter import _expected_transition


BEFORE = "0.1.122-issue.703.9.8"
EXPECTED = "0.1.122-issue.703.10.0"
OPERATION = ("task", "--increment", "merge-integration-failed")


class ManualMitVersionContractTests(unittest.TestCase):
  def test_development_version_parser_accepts_r_zero(self):
    self.assertIsNotNone(
      _TASK.fullmatch(EXPECTED),
      "MIT FAIL Q+1/R=0 must be representable in canonical version grammar",
    )

  def test_version_adapter_accepts_required_failure_transition(self):
    self.assertTrue(
      _expected_transition(BEFORE, EXPECTED, OPERATION),
      "MIT FAIL version gate must certify Q+1 and R=0",
    )

  def test_real_engine_failure_transition_resets_iteration_to_zero(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      path = root / ".ci" / "engine-version"
      path.parent.mkdir(parents=True)
      path.write_text(BEFORE + "\n", encoding="utf-8")
      before, after = transition_engine_version(
        root, operation="task --increment merge-integration-failed"
      )
      self.assertEqual(before, BEFORE)
      self.assertEqual(
        after, EXPECTED,
        "repository-owned version adapter must yield R=0, not R=1",
      )
      self.assertEqual(path.read_text(encoding="utf-8"), EXPECTED + "\n")


if __name__ == "__main__":
  unittest.main()
