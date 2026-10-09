"""The hosted plan must distinguish requested candidate from trigger commit."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class HostedPlanCandidateTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name)
    self.git("init", "-q")
    self.git("config", "user.email", "tests@example.invalid")
    self.git("config", "user.name", "Test Runner")
    (self.root / "source.py").write_text("value = 1\n")
    self.git("add", "source.py")
    self.git("commit", "-qm", "candidate")
    self.candidate = self.git("rev-parse", "HEAD")
    spec = importlib.util.spec_from_file_location(
      "rwf_on_demand_plan", ROOT / "scripts/on-demand-ci-plan.py",
    )
    self.assertIsNotNone(spec)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    self.plan = module.plan_invocation

  def tearDown(self):
    self.temp.cleanup()

  def git(self, *args):
    return subprocess.check_output(
      ["git", "-C", str(self.root), *args], text=True,
    ).strip()

  def invoke(self, stage="GREEN-testing"):
    marker = self.root / ".ci/run"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(stage + " " + self.git("rev-parse", "HEAD") + "\n")
    self.git("add", ".ci/run")
    self.git("commit", "-qm", "invoke hosted tests")

  def test_candidate_sha_is_parent_not_invocation_commit(self):
    self.invoke()
    invocation_sha = self.git("rev-parse", "HEAD")
    result = self.plan(self.root)
    self.assertEqual(result["stage"], "GREEN-testing")
    self.assertEqual(result["tested_sha"], self.candidate)
    self.assertEqual(result["previous_tip"], self.candidate)
    self.assertEqual(result["invocation_sha"], invocation_sha)
    self.assertNotEqual(result["tested_sha"], result["invocation_sha"])

  def test_retry_binds_to_immediate_parent_not_first_request(self):
    self.invoke()
    first_request = self.git("rev-parse", "HEAD")
    self.invoke(stage="regression-testing")
    result = self.plan(self.root)
    self.assertEqual(result["tested_sha"], first_request)
    self.assertEqual(result["stage"], "regression-testing")
    self.assertEqual(result["invocation_sha"], self.git("rev-parse", "HEAD"))


if __name__ == "__main__":
  unittest.main()
