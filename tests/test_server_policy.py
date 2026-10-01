from pathlib import Path
import tempfile
import unittest

from repo_workflow.config import load_config
from repo_workflow.prelim import PRELIM_BRANCH, merge_accepted, start_prelim
from repo_workflow.server_policy import (
  IntegrationAdmission,
  ServerPolicyError,
  check_integration_admission,
  required_github_rules,
)
from tests.support import RepoFixture


class ServerPolicyTests(unittest.TestCase):
  def make_candidate(self, root: Path) -> tuple[RepoFixture, str]:
    fx = RepoFixture(root)
    (root / "feature.txt").write_text("accepted\n", encoding="utf-8")
    fx.commit("accepted task")
    fx.push()
    config = load_config(root)
    start_prelim(root, config)
    candidate = merge_accepted(root, "issue-1-test")
    return fx, candidate

  def admission(self, candidate: str, **updates) -> IntegrationAdmission:
    values = {
      "source_branch": PRELIM_BRANCH,
      "base_branch": "main",
      "candidate_sha": candidate,
      "validation_sha": candidate,
      "validation_passed": True,
      "integration_authorized": True,
    }
    values.update(updates)
    return IntegrationAdmission(**values)

  def test_current_exact_validated_authorized_prelim_is_admitted(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      _fx, candidate = self.make_candidate(root)
      check_integration_admission(root, self.admission(candidate))

  def test_issue_branch_cannot_satisfy_main_integration_contract(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      _fx, candidate = self.make_candidate(root)
      with self.assertRaisesRegex(ServerPolicyError, "source must be prelim-main"):
        check_integration_admission(
          root,
          self.admission(candidate, source_branch="issue-1-test"),
        )

  def test_stale_prelim_is_rejected_after_server_main_advances(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx, candidate = self.make_candidate(root)
      fx._run("switch", "-c", "server-advance", "main")
      (root / "server.txt").write_text("advance\n", encoding="utf-8")
      fx.commit("server main advance")
      fx._run("push", "origin", "HEAD:main")
      fx._run("switch", PRELIM_BRANCH)
      with self.assertRaisesRegex(ServerPolicyError, "candidate is stale"):
        check_integration_admission(root, self.admission(candidate))

  def test_validation_must_match_exact_candidate_and_pass(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx, candidate = self.make_candidate(root)
      old = fx._run("rev-parse", f"{candidate}^1").stdout.strip()
      with self.assertRaisesRegex(ServerPolicyError, "exact candidate SHA"):
        check_integration_admission(
          root,
          self.admission(candidate, validation_sha=old),
        )
      with self.assertRaisesRegex(ServerPolicyError, "missing or failed"):
        check_integration_admission(
          root,
          self.admission(candidate, validation_passed=False),
        )

  def test_authorization_is_fail_closed_without_defining_its_storage(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      _fx, candidate = self.make_candidate(root)
      with self.assertRaisesRegex(ServerPolicyError, "authorization is absent"):
        check_integration_admission(
          root,
          self.admission(candidate, integration_authorized=False),
        )

  def test_required_rules_cover_main_and_stable_tag_boundaries(self):
    rules = required_github_rules()
    self.assertTrue(rules["main"]["requirePullRequest"])
    self.assertTrue(rules["main"]["blockDirectPush"])
    self.assertTrue(rules["main"]["blockForcePush"])
    self.assertTrue(rules["main"]["blockDeletion"])
    self.assertTrue(rules["main"]["requireCurrentBase"])
    self.assertEqual(rules["stableTags"]["creation"], "controlled finalizer only")
    self.assertTrue(rules["stableTags"]["blockUpdate"])
    self.assertTrue(rules["stableTags"]["blockDeletion"])


if __name__ == "__main__":
  unittest.main()
