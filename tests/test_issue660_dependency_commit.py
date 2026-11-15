"""Direct provider synchronization commits just its durable CSV output."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.dependency_sync_cli import dependency_sync_command
from repo_workflow.state_store import WriterIdentity


def git(root, *args):
  return subprocess.run(["git", *args], cwd=root, capture_output=True,
                        check=True).stdout.decode("utf-8", "strict")


class DependencyCommitTests(unittest.TestCase):
  def setUp(self):
    area = tempfile.TemporaryDirectory()
    self.addCleanup(area.cleanup)
    self.root = Path(area.name)
    git(self.root, "init", "-q")
    git(self.root, "config", "user.name", "Test")
    git(self.root, "config", "user.email", "test@example.invalid")
    state = self.root / ".repoworkflow/tickets.csv"
    state.parent.mkdir()
    state.write_text("issue,title,dependencies\n2,Two,\n64,Sixty Four,2\n")
    (self.root / "unrelated").write_text("initial\n")
    git(self.root, "add", ".")
    git(self.root, "commit", "-qm", "initial")

  @patch("repo_workflow.dependency_sync_cli.runtime_writer_identity",
         return_value=WriterIdentity("fixture", "session"))
  @patch("repo_workflow.dependency_sync_cli.read_ticket_sync_state",
         return_value=("Renamed Sixty Four", ()))
  @patch("repo_workflow.dependency_sync_cli.load_config", return_value={})
  def test_from_tickets_commits_only_csv_and_keeps_user_stage(self, *_):
    (self.root / "unrelated").write_text("staged\n")
    git(self.root, "add", "unrelated")
    (self.root / "unrelated").write_text("unstaged\n")
    before = git(self.root, "rev-parse", "HEAD").strip()
    self.assertEqual(dependency_sync_command(self.root,
      ("64", "dependency", "from-tickets", "--replace")), 0)
    after = git(self.root, "rev-parse", "HEAD").strip()
    self.assertNotEqual(before, after)
    self.assertEqual(git(self.root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"),
                     ".repoworkflow/tickets.csv\n")
    self.assertIn("64,Renamed Sixty Four,", git(self.root, "show", "HEAD:.repoworkflow/tickets.csv"))
    self.assertEqual(git(self.root, "show", ":unrelated"), "staged\n")
    self.assertEqual((self.root / "unrelated").read_text(), "unstaged\n")

  @patch("repo_workflow.dependency_sync_cli.runtime_writer_identity",
         return_value=WriterIdentity("fixture", "session"))
  @patch("repo_workflow.dependency_sync_cli.read_ticket_sync_state",
         return_value=("Sixty Four", (2,)))
  @patch("repo_workflow.dependency_sync_cli.load_config", return_value={})
  def test_compare_is_read_only(self, *_):
    before = git(self.root, "rev-parse", "HEAD")
    self.assertEqual(dependency_sync_command(self.root,
      ("64", "dependency", "from-tickets", "--compare")), 0)
    self.assertEqual(git(self.root, "rev-parse", "HEAD"), before)
    self.assertEqual(git(self.root, "status", "--porcelain"), "")
