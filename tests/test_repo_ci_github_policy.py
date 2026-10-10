from pathlib import Path
import tempfile
import unittest

from repo_workflow.repo_ci_github_policy import check_github_policy


def request():
  return {
    "contract_version": 1,
    "operation": "check-policy",
    "invocation_id": "attempt-1",
    "candidate": {"repository": "owner/repo", "commit": "abc", "base": "def"},
    "requirements": {"stages": [], "capabilities": [], "artifacts": []},
    "inputs": {"policies": ["canonical-bootstrap"]},
  }


class GitHubPolicyAdapterTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.root = Path(self.tmp.name)
    self.engine = self.root / "RepoWorkflow"
    self.canonical = self.engine / "templates" / "github" / "ci.yml"
    self.consumer = self.root / ".github" / "workflows" / "ci.yml"
    self.canonical.parent.mkdir(parents=True)
    self.consumer.parent.mkdir(parents=True)
    self.canonical.write_text("name: CI\n")
    self.consumer.write_text("name: CI\n")

  def call(self, value):
    return check_github_policy(value, root=self.root, engine_root=self.engine)

  def test_valid_policy_observation_preserves_identity(self):
    value = request()
    result = self.call(value)
    self.assertEqual(result["status"], "ok")
    self.assertIs(result["candidate"], value["candidate"])
    self.assertEqual(result["invocation_id"], "attempt-1")
    self.assertEqual(result["operation"], "check-policy")
    self.assertEqual(result["artifacts"], [])
    self.assertEqual(result["observations"]["policies"], [
      {"id": "canonical-bootstrap", "satisfied": True}
    ])
    self.assertNotIn("PASS", str(result))

  def test_modified_bootstrap_reports_unsatisfied_without_authority(self):
    self.consumer.write_text("name: injected\n")
    before = self.consumer.read_bytes()
    result = self.call(request())
    self.assertEqual(result["status"], "ok")
    self.assertFalse(result["observations"]["policies"][0]["satisfied"])
    self.assertEqual(result["diagnostics"][0]["code"], "prerequisite-unavailable")
    self.assertEqual(self.consumer.read_bytes(), before)

  def test_missing_workflow_is_observed_without_creating_files(self):
    self.consumer.unlink()
    result = self.call(request())
    self.assertFalse(result["observations"]["policies"][0]["satisfied"])
    self.assertFalse(self.consumer.exists())

  def test_invalid_envelopes_are_rejected_before_inspection(self):
    cases = [None, [], {}, {**request(), "contract_version": True},
             {**request(), "contract_version": 2},
             {**request(), "operation": "publish"},
             {**request(), "operation": []},
             {**request(), "invocation_id": ""},
             {**request(), "candidate": {"repository": "owner/repo"}},
             {**request(), "inputs": {"policies": ["other"]}},
             {**request(), "inputs": {"policies": [{}]}},
             {**request(), "inputs": {"policies": ["canonical-bootstrap"] * 2}},
             {**request(), "unexpected": 1},
             {**request(), "requirements": {"stages": []}}]
    for case in cases:
      with self.subTest(case=case):
        result = self.call(case)
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["observations"])
        self.assertEqual(result["artifacts"], [])

  def test_unsupported_required_capability_fails_closed(self):
    value = request()
    value["requirements"]["capabilities"] = ["git-admin"]
    result = self.call(value)
    self.assertEqual(result["status"], "error")
    self.assertEqual(result["diagnostics"][0]["code"], "capability-unavailable")

  def test_declared_migration_workflows_are_exact(self):
    legacy = self.consumer.parent / "legacy.yml"
    legacy.write_text("name: Legacy\n")
    result = check_github_policy(
      request(), root=self.root, engine_root=self.engine,
      migration_workflows=["legacy.yml"],
    )
    self.assertTrue(result["observations"]["policies"][0]["satisfied"])
    legacy.write_text("name: Modified\n")
    self.assertTrue(result["observations"]["policies"][0]["satisfied"])
    (self.consumer.parent / "undeclared.yml").write_text("name: Bad\n")
    result = check_github_policy(
      request(), root=self.root, engine_root=self.engine,
      migration_workflows=["legacy.yml"],
    )
    self.assertFalse(result["observations"]["policies"][0]["satisfied"])


if __name__ == "__main__":
  unittest.main()
