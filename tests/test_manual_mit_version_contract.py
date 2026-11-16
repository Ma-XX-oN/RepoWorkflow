"""Independent required Q/R version contract probes for RWF #703.

These probes verify the implementation-revision transition used when preparing
repairs after manual rejection. Recording the rejection itself keeps the version.
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
      "prepared repair Q+1/R=0 must be representable in canonical version grammar",
    )

  def test_version_adapter_accepts_implementation_revision_transition(self):
    self.assertTrue(
      _expected_transition(BEFORE, EXPECTED, OPERATION),
      "implementation revision gate must certify Q+1 and R=0",
    )

  def test_real_engine_implementation_revision_resets_reintegration_to_zero(self):
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
