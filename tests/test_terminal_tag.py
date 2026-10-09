"""Real-Git contract tests for immutable regression/integration result tags."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.terminal_tag import TerminalTagError, publish_terminal_tag


VERSION = "0.1.121-issue.545.0.1"


class TerminalTagTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    base = Path(self.temp.name)
    self.root = base / "work"
    self.remote = base / "remote.git"
    self.git_in(base, "init", "--bare", str(self.remote))
    self.git_in(base, "init", "-b", "issue-545-test", str(self.root))
    self.git("config", "user.name", "Test")
    self.git("config", "user.email", "test@example.invalid")
    (self.root / "source.txt").write_text("original source\n")
    self.git("add", "source.txt")
    self.git("commit", "-m", "candidate")
    self.candidate = self.git("rev-parse", "HEAD")
    self.git("remote", "add", "origin", str(self.remote))
    self.git("push", "origin", "HEAD:refs/heads/issue-545-test")

  def git_in(self, cwd, *args):
    result = subprocess.run(
      ["git", *args], cwd=cwd, text=True, capture_output=True, check=False,
    )
    if result.returncode:
      raise AssertionError(result.stderr)
    return result.stdout.strip()

  def git(self, *args):
    return self.git_in(self.root, *args)

  def issue_marker(self):
    path = self.root / ".ci/run"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("regression-testing " + self.git("rev-parse", "HEAD") + "\n")
    self.git("add", ".ci/run")
    self.git("commit", "-m", "dedicated CI request")

  def published(self, tag):
    result = self.git(\n      "ls-remote", "--tags", "origin",\n      "refs/tags/" + tag, "refs/tags/" + tag + "^{}",\n    )
    return dict(
      (line.split("\t", 1)[1], line.split("\t", 1)[0])
      for line in result.splitlines() if "\t" in line
    )

  def issue_tag(self, outcome, **overrides):
    args = {
      "remote": "origin", "version": VERSION,
      "candidate": self.candidate, "outcome": outcome,
    }
    args.update(overrides)
    return publish_terminal_tag(self.root, **args)

  def test_pass_tag_targets_original_commit_before_multiple_requests(self):
    self.issue_marker()
    self.issue_marker()
    latest = self.git("rev-parse", "HEAD")
    tag = self.issue_tag("PASS")
    self.assertEqual(tag, "v" + VERSION)
    self.assertEqual(
      self.git("rev-parse", "refs/tags/" + tag + "^{commit}"),
      self.candidate,
    )
    self.assertNotEqual(latest, self.candidate)
    self.assertEqual(
      self.published(tag)["refs/tags/" + tag + "^{}"], self.candidate,
    )

  def test_repeating_same_outcome_is_idempotent(self):
    tag = self.issue_tag("PASS")
    first = self.git("rev-parse", "refs/tags/" + tag)
    self.assertEqual(self.issue_tag("PASS"), tag)
    self.assertEqual(self.git("rev-parse", "refs/tags/" + tag), first)

  def test_complete_failure_tag_points_to_candidate(self):
    tag = self.issue_tag("FAIL")
    self.assertEqual(tag, "v" + VERSION + "-CI-FAIL")
    self.assertEqual(
      self.published(tag)["refs/tags/" + tag + "^{}"], self.candidate,
    )

  def test_incomplete_never_creates_a_tag(self):
    self.assertIsNone(self.issue_tag("INCOMPLETE"))
    self.assertEqual(self.git("tag", "--list"), "")

  def test_opposite_outcome_cannot_be_published(self):
    self.issue_tag("FAIL")
    with self.assertRaisesRegex(TerminalTagError, "opposite"):
      self.issue_tag("PASS")

  def test_malformed_version_or_candidate_fails_without_tag(self):
    with self.assertRaisesRegex(TerminalTagError, "development version"):
      self.issue_tag("PASS", version="0.1.121")
    with self.assertRaisesRegex(TerminalTagError, "full original candidate"):
      self.issue_tag("FAIL", candidate="abc")
    with self.assertRaisesRegex(TerminalTagError, "unknown terminal"):
      self.issue_tag("SKIPPED")
    self.assertEqual(self.git("tag", "--list"), "")

  def test_existing_remote_different_target_is_rejected(self):
    self.issue_marker()
    self.git("tag", "-a", "v" + VERSION, "HEAD", "-m", "conflict")
    self.git("push", "origin", "refs/tags/v" + VERSION)
    with self.assertRaisesRegex(TerminalTagError, "different commit"):
      self.issue_tag("PASS")

  def test_unannotated_terminal_tag_is_rejected(self):
    self.git("tag", "v" + VERSION, self.candidate)
    with self.assertRaisesRegex(TerminalTagError, "annotated"):
      self.issue_tag("PASS")

  def test_local_replay_after_remote_publication(self):
    tag = self.issue_tag("PASS")
    self.git("tag", "-d", tag)
    self.assertEqual(self.issue_tag("PASS"), tag)
    self.assertEqual(
      self.published(tag)["refs/tags/" + tag + "^{}"], self.candidate,
    )


if __name__ == "__main__":
  unittest.main()
