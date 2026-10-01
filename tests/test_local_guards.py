from pathlib import Path
import tempfile
import unittest

from repo_workflow.config import load_config
from repo_workflow.local_guards import (
  LocalGuardError,
  check_commit,
  check_push,
  check_rebase,
  install_hooks,
)
from repo_workflow.prelim import PRELIM_BRANCH, merge_accepted, start_prelim
from tests.support import RepoFixture


ZERO = "0" * 40


class LocalGuardTests(unittest.TestCase):
  def test_issue_commit_passes_and_tracking_main_commit_is_blocked(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      check_commit(root)
      fx._run("switch", "main")
      with self.assertRaisesRegex(LocalGuardError, "direct commits"):
        check_commit(root)

  def test_direct_main_push_and_stable_tag_creation_are_blocked(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      head = fx.head()
      with self.assertRaisesRegex(LocalGuardError, "direct push"):
        check_push(
          root,
          f"refs/heads/issue-1-test {head} refs/heads/main {ZERO}\n",
        )
      with self.assertRaisesRegex(LocalGuardError, "protected server finalizer"):
        check_push(
          root,
          f"refs/tags/v1.0.0 {head} refs/tags/v1.0.0 {ZERO}\n",
        )

  def test_malformed_workflow_tag_and_immutable_tag_delete_are_blocked(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      head = fx.head()
      with self.assertRaisesRegex(LocalGuardError, "malformed"):
        check_push(
          root,
          f"refs/tags/vbad {head} refs/tags/vbad {ZERO}\n",
        )
      with self.assertRaisesRegex(LocalGuardError, "may not be deleted"):
        check_push(
          root,
          f"(delete) {ZERO} refs/tags/v1.0.0-issue.1.0.1 {head}\n",
        )

  def test_stale_prelim_push_is_blocked(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      (root / "feature.txt").write_text("accepted\n", encoding="utf-8")
      fx.commit("accepted issue work")
      fx.push()
      config = load_config(root)
      start_prelim(root, config)
      candidate = merge_accepted(root, "issue-1-test")

      fx._run("switch", "-c", "server-advance", "main")
      (root / "server.txt").write_text("advance\n", encoding="utf-8")
      fx.commit("server main advance")
      fx._run("push", "origin", "HEAD:main")
      fx._run("switch", PRELIM_BRANCH)

      with self.assertRaisesRegex(LocalGuardError, "stale prelim-main"):
        check_push(
          root,
          f"refs/heads/{PRELIM_BRANCH} {candidate} refs/heads/{PRELIM_BRANCH} {ZERO}\n",
        )

  def test_rebase_that_rewrites_tagged_candidate_is_blocked(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      tagged = fx.head()
      fx._run("tag", "v1.0.0-issue.1.0.1", tagged)
      (root / "next.txt").write_text("next\n", encoding="utf-8")
      fx.commit("later work")
      with self.assertRaisesRegex(LocalGuardError, "rewrite tagged workflow candidate"):
        check_rebase(root, "main")

  def test_hook_install_refuses_unrelated_existing_hook_without_force(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      hooks = root / ".git" / "hooks"
      hooks.mkdir(exist_ok=True)
      existing = hooks / "pre-push"
      existing.write_text("#!/bin/sh\necho foreign\n", encoding="utf-8")
      with self.assertRaisesRegex(LocalGuardError, "existing hook differs"):
        install_hooks(root)
      installed = install_hooks(root, force=True)
      self.assertEqual({path.name for path in installed}, {"pre-commit", "pre-push", "pre-rebase"})
      self.assertNotIn("foreign", existing.read_text(encoding="utf-8"))


if __name__ == "__main__":
  unittest.main()
