"""Independent invocation acceptance probes against #540's shipped contract.

These do not install or copy an upstream implementation. Until the #540
module is in the candidate, the checks remain explicitly PENDING.
"""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "repo_workflow" / "ci_invocation.py"
STAGES = ("RED-testing", "temp-testing", "GREEN-testing",
          "regression-testing", "integration-testing")


class InvocationContractAcceptanceTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    if not MODULE.exists():
      raise unittest.SkipTest("PENDING: #540 source not in this candidate")
    from repo_workflow.ci_invocation import (  # noqa: PLC0415
      CiInvocationError, parse_invocation, verify_invocation,
    )
    cls.parser = staticmethod(parse_invocation)
    cls.verify = staticmethod(verify_invocation)
    cls.error = CiInvocationError

  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    self.git("init", "-q")
    self.git("config", "user.name", "Independent Fixture")
    self.git("config", "user.email", "fixture@example.invalid")
    (self.root / "source.txt").write_text("baseline\n")
    self.git("add", "source.txt")
    self.git("commit", "-qm", "initial")
    self.base = self.git("rev-parse", "HEAD")

  def git(self, *args):
    return subprocess.check_output(
      ["git", "-C", str(self.root), *args], text=True, timeout=30,
    ).strip()

  def invocation(self, stage="GREEN-testing", previous=None, source_change=False):
    marker = self.root / ".ci/run"
    marker.parent.mkdir(exist_ok=True)
    marker.write_text(f"{stage} {previous or self.git('rev-parse', 'HEAD')}\n")
    self.git("add", ".ci/run")
    if source_change:
      (self.root / "source.txt").write_text("changed\n")
      self.git("add", "source.txt")
    self.git("commit", "-qm", "dedicated test invocation")

  def test_five_stages_plus_invalid_and_noncanonical_sha(self):
    for stage in STAGES:
      with self.subTest(stage=stage):
        actual = self.parser(f"{stage} {'a' * 40}\n")
        self.assertEqual((actual.stage, actual.previous_tip), (stage, "a" * 40))
    for request in ("GREEN-testing short", "bad-testing " + "a" * 40,
                    "GREEN-testing " + "A" * 40,
                    "GREEN-testing " + "a" * 40 + "\nextra"):
      with self.subTest(request=request):
        with self.assertRaises(self.error):
          self.parser(request)

  def test_dedicated_commit_matches_parent(self):
    self.invocation()
    self.assertEqual(self.verify(self.root).previous_tip, self.base)

  def test_stale_marker_rejected(self):
    self.invocation(previous="f" * 40)
    with self.assertRaises(self.error):
      self.verify(self.root)

  def test_mixed_source_mutation_rejected(self):
    self.invocation(source_change=True)
    with self.assertRaises(self.error):
      self.verify(self.root)

  def test_retry_binds_immediate_previous_tip(self):
    self.invocation()
    invocation_tip = self.git("rev-parse", "HEAD")
    self.invocation()
    self.assertEqual(self.verify(self.root).previous_tip, invocation_tip)

  def test_uncommitted_tamper_cannot_change_accepted_request(self):
    self.invocation()
    (self.root / ".ci/run").write_text("RED-testing " + "f" * 40 + "\n")
    verified = self.verify(self.root)
    self.assertEqual(verified.stage, "GREEN-testing")
    self.assertEqual(verified.previous_tip, self.base)


if __name__ == "__main__":
  unittest.main()
