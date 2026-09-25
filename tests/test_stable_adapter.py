from pathlib import Path
import json
import tempfile
import unittest

from repo_workflow.github_adapter import github_mode
from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]


class StableAdapterTests(unittest.TestCase):
  def make(self):
    td = tempfile.TemporaryDirectory()
    root = Path(td.name) / "repo"
    root.mkdir()
    fixture = RepoFixture(root)
    return td, root, fixture

  def test_main_push_selects_stable_mode(self):
    td, root, fx = self.make()
    with td:
      event_path = root.parent / "event.json"
      event_path.write_text(json.dumps({"after": fx.head()}), encoding="utf-8")
      self.assertEqual(
        github_mode(root, "push", event_path, "main", "main"),
        "stable",
      )

  def test_manual_dispatch_selects_development_mode(self):
    td, root, _fx = self.make()
    with td:
      event_path = root.parent / "event.json"
      event_path.write_text("{}", encoding="utf-8")
      self.assertEqual(
        github_mode(root, "workflow_dispatch", event_path, "issue-1-test", "main"),
        "development",
      )

  def test_nonrequested_issue_push_selects_none(self):
    td, root, fx = self.make()
    with td:
      before = fx.head()
      (root / "ordinary.txt").write_text("ordinary\n", encoding="utf-8")
      after = fx.commit("ordinary")
      event_path = root.parent / "event.json"
      event_path.write_text(
        json.dumps({"before": before, "after": after}),
        encoding="utf-8",
      )
      self.assertEqual(
        github_mode(root, "push", event_path, "issue-1-test", "main"),
        "none",
      )

  def test_canonical_template_carries_stable_mode_end_to_end(self):
    text = (ROOT / "templates" / "github" / "ci.yml").read_text(encoding="utf-8")
    for value in (
      "github-mode",
      "stable-preflight",
      "materialize-artifacts --stable",
      "stable-run",
      "stable-finalize",
    ):
      self.assertIn(value, text)
    self.assertIn("needs.policy.outputs.mode != 'none'", text)


if __name__ == "__main__":
  unittest.main()
