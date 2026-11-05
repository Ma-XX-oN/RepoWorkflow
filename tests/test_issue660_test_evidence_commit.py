"""Durable test phases must commit only their own result log."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.test_cli import run_test


class TestEvidenceCommitTests(unittest.TestCase):
  def setUp(self):
    area = tempfile.TemporaryDirectory()
    self.addCleanup(area.cleanup)
    self.root = Path(area.name)
    self.git("init", "-q")
    self.git("config", "user.name", "Fixture")
    self.git("config", "user.email", "fixture@example.invalid")
    self.git("checkout", "-qb", "issue-660-validation")
    (self.root / "unrelated.txt").write_text("original\n", encoding="utf-8")
    self.git("add", "unrelated.txt")
    self.git("commit", "-qm", "initial")

  def git(self, *args):
    return subprocess.run(
      ["git", *args], cwd=self.root, capture_output=True, check=True,
    ).stdout.decode("utf-8", "strict")

  def test_every_local_test_phase_commits_its_own_evidence(self):
    evidence = ".repoworkflow/validation/testResults-660.jsonl"
    path = self.root / evidence
    path.parent.mkdir(parents=True, exist_ok=True)
    (self.root / "unrelated.txt").write_text("staged\n", encoding="utf-8")
    self.git("add", "unrelated.txt")
    (self.root / "unrelated.txt").write_text("unstaged\n", encoding="utf-8")
    for stage in ("RED", "GREEN", "temporary", "regression", "integration"):
      with self.subTest(stage=stage):
        def write_evidence(*_args, **_kwargs):
          with path.open("a", encoding="utf-8") as stream:
            stream.write(stage + "\n")
          return 1 if stage == "regression" else 0
        before = self.git("rev-parse", "HEAD")
        with patch("repo_workflow.test_cli._run_test_impl", side_effect=write_evidence):
          actual = run_test(self.root, stage, remote=False, engine_root=self.root)
        self.assertEqual(actual, 1 if stage == "regression" else 0)
        self.assertNotEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(
          self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"),
          evidence + "\n",
        )
        self.assertEqual(self.git("show", ":unrelated.txt"), "staged\n")
        self.assertEqual((self.root / "unrelated.txt").read_text(), "unstaged\n")

  def test_no_log_means_no_new_commit(self):
    before = self.git("rev-parse", "HEAD")
    with patch("repo_workflow.test_cli._run_test_impl", return_value=2):
      self.assertEqual(run_test(self.root, "regression", remote=False,
                                engine_root=self.root), 2)
    self.assertEqual(self.git("rev-parse", "HEAD"), before)
