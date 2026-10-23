"""Dedicated Git commits must exclude separately staged test evidence."""
import json
import subprocess
import unittest

from tests import test_test_cli as fixture


class DedicatedCommitTests(unittest.TestCase):
  setUp = fixture.TestCliContract.setUp
  tearDown = fixture.TestCliContract.tearDown
  git = fixture.TestCliContract.git
  cli = fixture.TestCliContract.cli
  remote = fixture.TestCliContract.remote
  _catalogue = fixture.TestCliContract._catalogue

  def _git_wire_path(self, path):
    # Resolve first: a lexical relative path may still escape via '..' or a link.
    return path.resolve().relative_to(self.root.resolve()).as_posix()

  def _staged_git_paths(self):
    # Git -z paths are UTF-8, slash-delimited and never C-quoted.
    result = subprocess.run(
      ["git", "-C", str(self.root), "diff", "--cached", "--name-only", "-z"],
      capture_output=True,
      check=True,
    )
    return [
      item.decode("utf-8")
      for item in result.stdout.split(b"\0")
      if item
    ]

  def _stage_log(self):
    path = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"result": "incomplete"}) + "\n")
    self.git("add", "-f", "--", str(path.relative_to(self.root)))
    return path

  def test_staged_audit_is_not_in_red_selection_commit(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-one",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    path = self._stage_log()
    result = self.cli("test", "RED", "issue-545-one")
    self.assertEqual(result.returncode, 2, result.stderr)
    self.assertEqual(
      self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"),
      ".ci/red-green.txt",
    )
    self.assertIn(self._git_wire_path(path), self._staged_git_paths())
    self.assertNotIn(
      self._git_wire_path(path),
      self.git("diff-tree", "--no-commit-id", "--name-only", "-r",
               "HEAD").splitlines(),
    )

  def test_staged_audit_is_not_in_hosted_request_commit(self):
    server = self.remote()
    path = self._stage_log()
    before = self.git("rev-parse", "HEAD")
    result = self.cli("test", "regression", "--remote")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(
      self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"),
      ".ci/run",
    )
    self.assertEqual(self.git("rev-parse", "HEAD^"), before)
    self.assertIn(self._git_wire_path(path), self._staged_git_paths())
    self.assertNotIn(
      self._git_wire_path(path),
      self.git("diff-tree", "--no-commit-id", "--name-only", "-r",
               "HEAD").splitlines(),
    )
    self.assertEqual(
      self.git("rev-parse", "HEAD"),
      __import__("subprocess").check_output(
        ["git", "--git-dir", str(server), "rev-parse",
         "refs/heads/issue-545-fixture"],
        text=True,
      ).strip(),
    )

  def test_staged_git_wire_paths_preserve_spaces_unicode_and_containment(self):
    path = self.root / "spaced directory" / "réglage 雪 .txt"
    path.parent.mkdir(parents=True)
    path.write_text("staged only\n", encoding="utf-8")
    self.git("add", "--", str(path.relative_to(self.root)))

    wire_path = self._git_wire_path(path)
    self.assertEqual(wire_path, "spaced directory/réglage 雪 .txt")
    self.assertEqual(self._staged_git_paths(), [wire_path])
    self.assertNotIn(wire_path.replace("/", "\\"), self._staged_git_paths())
    self.assertNotIn(
      "spaced directory/réglage 雪 .txt.backup",
      self._staged_git_paths(),
    )
    for escaped in (
      self.root.parent / "outside.txt",
      self.root / ".." / "outside.txt",
    ):
      with self.subTest(escaped=escaped):
        with self.assertRaises(ValueError):
          self._git_wire_path(escaped)


if __name__ == "__main__":
  unittest.main()
