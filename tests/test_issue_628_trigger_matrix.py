"""Black-box marker contract probes for issue #628; hosted observations separate."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.ci_invocation import CiInvocationError, verify_invocation


class TriggerMatrixTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.root = Path(self.tmp.name)
    self.git("init", "-q")
    self.git("config", "user.email", "fixture@example.invalid")
    self.git("config", "user.name", "Fixture")
    (self.root / "source").write_text("initial\n")
    self.git("add", "source")
    self.git("commit", "-qm", "initial")
    self.base = self.git("rev-parse", "HEAD")

  def git(self, *args):
    return subprocess.check_output(
      ["git", "-C", str(self.root), *args], text=True
    ).strip()

  def invoke(self, previous=None, marker=None, mixed=False):
    (self.root / ".ci").mkdir(exist_ok=True)
    (self.root / ".ci/run").write_text(
      marker if marker is not None else
      "regression-testing " + (previous or self.git("rev-parse", "HEAD")) + "\n"
    )
    if mixed:
      (self.root / "source").write_text("modified\n")
      self.git("add", "source")
    self.git("add", ".ci/run")
    self.git("commit", "-qm", "invoke")
    return self.git("rev-parse", "HEAD")

  def test_T00_zero_requests(self):
    with self.assertRaises(CiInvocationError):
      verify_invocation(self.root)

  def test_T01_one_request_binds_parent(self):
    tip = self.invoke()
    self.assertNotEqual(tip, self.base)
    self.assertEqual(verify_invocation(self.root).previous_tip, self.base)

  def test_T02_two_requests_bind_distinct_parents(self):
    first = self.invoke()
    second = self.invoke()
    self.assertNotEqual(first, second)
    self.assertEqual(verify_invocation(self.root).previous_tip, first)

  def test_T03_retry_new_request_uses_latest_parent(self):
    missed = self.invoke()
    self.invoke()
    self.assertEqual(verify_invocation(self.root).previous_tip, missed)

  def ordinary_push(self):
    (self.root / "source").write_text("changed\n")
    self.git("commit", "-qam", "ordinary push")
    with self.assertRaises(CiInvocationError):
      verify_invocation(self.root)

  def test_T04_ordinary_push(self):
    self.ordinary_push()

  def test_T05_main_ordinary_push(self):
    self.git("checkout", "-qb", "main")
    self.ordinary_push()

  def test_T06_prelim_main_ordinary_push(self):
    self.git("checkout", "-qb", "prelim-main")
    self.ordinary_push()

  def test_T07_read_does_not_commit(self):
    before = self.git("rev-parse", "HEAD")
    with self.assertRaises(CiInvocationError):
      verify_invocation(self.root)
    self.assertEqual(self.git("rev-parse", "HEAD"), before)

  def test_T08_worktree_tamper_does_not_change_request(self):
    self.invoke()
    (self.root / ".ci/run").write_text("RED-testing " + "f" * 40 + "\n")
    self.assertEqual(verify_invocation(self.root).stage, "regression-testing")

  def test_T09_malformed_marker_rejected(self):
    for marker in ("unknown " + "a" * 40,
                   "RED-testing broken",
                   "RED-testing " + "a" * 40 + "\n\n"):
      with self.subTest(marker=marker):
        self.invoke(marker=marker)
        with self.assertRaises(CiInvocationError):
          verify_invocation(self.root)
        self.git("reset", "--hard", self.base)

  def test_T10_changed_candidate_rejected(self):
    self.invoke(previous="f" * 40)
    with self.assertRaisesRegex(CiInvocationError, "prior branch tip"):
      verify_invocation(self.root)

  def test_T11_mixed_source_request_rejected(self):
    self.invoke(mixed=True)
    with self.assertRaisesRegex(CiInvocationError, "only .ci/run"):
      verify_invocation(self.root)

  def test_T12_merge_ancestry_rejected(self):
    original = self.git("symbolic-ref", "--short", "HEAD")
    self.git("checkout", "-qb", "side")
    (self.root / "side").write_text("side\n")
    self.git("add", "side")
    self.git("commit", "-qm", "side")
    self.git("checkout", "-q", original)
    self.invoke()
    self.git("merge", "-q", "--no-ff", "-m", "merge", "side")
    with self.assertRaises(CiInvocationError):
      verify_invocation(self.root)

  def test_T13_multiple_committed_requests_identity(self):
    first = self.invoke()
    second = self.invoke()
    self.assertEqual(verify_invocation(self.root).previous_tip, first)
    self.assertNotEqual(first, second)

  def test_T14_unapproved_ref_requires_provider_test(self):
    self.invoke()
    self.assertEqual(verify_invocation(self.root).previous_tip, self.base)
    # Parser has no ref input; this does NOT test GitHub ref filtering.

  def test_T15_duplicate_delivery_requires_provider_test(self):
    head = self.invoke()
    self.assertEqual(verify_invocation(self.root), verify_invocation(self.root))
    self.assertEqual(self.git("rev-parse", "HEAD"), head)
    # Repeated parsing does NOT establish hosted idempotency.


if __name__ == "__main__":
  unittest.main()
