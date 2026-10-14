"""Black-box engine-owned version adapter transition contract."""
from pathlib import Path
import tempfile
import unittest

from repo_workflow.engine_version_adapter import (
  EngineVersionError, read_engine_version, transition_engine_version,
)


class EngineVersionAdapterTests(unittest.TestCase):
  def setUp(self):
    temp = tempfile.TemporaryDirectory()
    self.addCleanup(temp.cleanup)
    self.root = Path(temp.name)
    (self.root / "VERSION").write_text("0.1.121\n")
    self.state = self.root / ".ci/engine-version"

  def transition(self, operation, issue=None):
    return transition_engine_version(
      self.root, operation=operation, issue=issue,
    )

  def test_stable_read_is_nonmutating(self):
    self.assertEqual(read_engine_version(self.root), "0.1.121")
    self.assertFalse(self.state.exists())

  def test_task_start_prepares_explicit_source_version(self):
    self.assertEqual(self.transition("task --issue", 572), (
      "0.1.121", "0.1.121-issue.572.0.1",
    ))
    self.assertEqual(read_engine_version(self.root),
                     "0.1.121-issue.572.0.1")
    self.assertEqual(self.state.read_text(),
                     "0.1.121-issue.572.0.1\n")

  def test_task_start_twice_does_not_overwrite_development_version(self):
    self.transition("task --issue", 572)
    prior = self.state.read_bytes()
    with self.assertRaises(EngineVersionError):
      self.transition("task --issue", 572)
    self.assertEqual(self.state.read_bytes(), prior)

  def test_regression_failure_increments_r_only(self):
    self.transition("task --issue", 572)
    self.assertEqual(self.transition(
      "task --increment CI-iteration",
    )[1], "0.1.121-issue.572.0.2")
    self.assertEqual(self.transition(
      "task --increment CI-iteration",
    )[1], "0.1.121-issue.572.0.3")

  def test_integration_rejection_increments_q_and_resets_r(self):
    self.transition("task --issue", 572)
    self.transition("task --increment CI-iteration")
    self.assertEqual(self.transition(
      "task --increment merge-integration-failed",
    )[1], "0.1.121-issue.572.1.1")

  def test_no_implicit_mutation_after_success_or_incomplete(self):
    self.transition("task --issue", 572)
    before = self.state.read_bytes()
    for op in ("PASS", "INCOMPLETE", "integration PASS"):
      with self.subTest(op=op):
        with self.assertRaises(EngineVersionError):
          self.transition(op)
        self.assertEqual(self.state.read_bytes(), before)

  def test_invalid_stable_version_fails_without_creating_state(self):
    self.root.joinpath("VERSION").write_text("0.1.121-extra\n")
    with self.assertRaisesRegex(EngineVersionError, "stable"):
      self.transition("task --issue", 572)
    self.assertFalse(self.state.exists())

  def test_noncanonical_task_version_is_not_repaired(self):
    self.state.parent.mkdir()
    self.state.write_text("0.1.121-issue.572.00.1\n")
    with self.assertRaisesRegex(EngineVersionError, "development"):
      self.transition("task --increment CI-iteration")
    self.assertEqual(self.state.read_text(),
                     "0.1.121-issue.572.00.1\n")

  def test_invalid_issue_cardinalities_do_not_mutate(self):
    for issue in (None, 0, -1, True, 1.5, "572"):
      with self.subTest(issue=issue):
        with self.assertRaises(EngineVersionError):
          self.transition("task --issue", issue)
        self.assertFalse(self.state.exists())

  def test_unrecognised_transition_rejected_without_changes(self):
    with self.assertRaisesRegex(EngineVersionError, "unsupported"):
      self.transition("integrate --increment patch")
    self.assertFalse(self.state.exists())

  def test_symlinked_storage_is_not_followed(self):
    external = self.root / "external"
    external.write_text("0.1.121-issue.572.0.1\n")
    self.state.parent.mkdir()
    try:
      self.state.symlink_to(external)
    except OSError:
      self.skipTest("symlink unsupported")
    with self.assertRaisesRegex(EngineVersionError, "symlink"):
      self.transition("task --increment CI-iteration")
    self.assertEqual(external.read_text(), "0.1.121-issue.572.0.1\n")


if __name__ == "__main__":
  unittest.main()
