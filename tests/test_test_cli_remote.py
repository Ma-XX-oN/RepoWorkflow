from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "repo_workflow.py"


class TestCliRemoteContract(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "work"
    self.root.mkdir()
    self.git("init", "-b", "issue-545-fixture")
    self.git("config", "user.name", "Test")
    self.git("config", "user.email", "test@example.invalid")
    (self.root / "README").write_text("source\n")
    self.git("add", "README")
    self.git("commit", "-m", "source")
    self.source = self.git("rev-parse", "HEAD").strip()

  def tearDown(self):
    self.temp.cleanup()

  def git(self, *args):
    completed = subprocess.run(
      ["git", "-C", str(self.root), *args],
      capture_output=True,
      text=True,
      check=True,
    )
    return completed.stdout.strip()

  def cli(self, *args):
    return subprocess.run(
      [sys.executable, str(CLI), "--root", str(self.root), *args],
      capture_output=True, text=True, check=False,
    )

  def remote(self):
    bare = Path(self.temp.name) / "server.git"
    subprocess.run(
      ["git", "init", "--bare", str(bare)],
      capture_output=True, check=True,
    )
    self.git("remote", "add", "origin", str(bare))
    self.git("push", "-u", "origin", "HEAD")
    return bare

  def _catalogue(self, path, *, issue_group):
    (self.root / "smoke_case.py").write_text(
      "import unittest\n"
      "class Smoke(unittest.TestCase):\n"
      "  def test_pass(self): self.assertTrue(True)\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
      "test-harnesses": {
        "unittest": {
          "command": "python",
          "layout": ["-m", "unittest", "$test"],
        },
      },
      "tests": [{
        "test-harness": "unittest",
        issue_group: {"type": "regression", "name": "smoke_case"},
      }],
      "aliases": {},
    }))

  def test_remote_request_and_retry_use_previous_tip(self):
    bare = self.remote()
    for stage in ("regression", "regression"):
      previous = self.git("rev-parse", "HEAD")
      request = self.cli("test", stage, "--remote")
      self.assertEqual(request.returncode, 0, request.stderr)
      self.assertEqual(
        (self.root / ".ci/run").read_text(),
        "regression-testing " + previous + "\n",
      )
      head = self.git("rev-parse", "HEAD")
      self.assertNotEqual(head, previous)
      self.assertEqual(self.git("rev-parse", "HEAD^"), previous)
      self.assertEqual(
        self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"),
        ".ci/run",
      )
      published = subprocess.run(
        ["git", "--git-dir", str(bare), "rev-parse",
         "refs/heads/issue-545-fixture"],
        text=True, capture_output=True, check=True,
      )
      self.assertEqual(published.stdout.strip(), head)

  def test_dirty_tree_rejects_remote_without_commit(self):
    self.remote()
    (self.root / "README").write_text("edited\n")
    result = self.cli("test", "regression", "--remote")
    self.assertEqual(result.returncode, 2)
    self.assertIn("working tree must be clean", result.stderr)
    self.assertEqual(self.git("rev-parse", "HEAD"), self.source)

  def test_remote_results_fetches_existing_log_only(self):
    self.remote()
    path = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    path.parent.mkdir(parents=True)
    record = {
      "testSHA": self.source, "kind": "regression",
      "result": "succeeded", "runner": "github-actions",
    }
    path.write_text(json.dumps(record) + "\n")
    self.git("add", ".repoworkflow/validation/testResults-545.jsonl")
    self.git("commit", "-m", "external result")
    self.git("push")
    path.unlink()
    current = self.git("rev-parse", "HEAD")
    result = self.cli("test", "results", "--remote")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(json.loads(result.stdout), record)
    self.assertEqual(self.git("rev-parse", "HEAD"), current)

  def test_remote_green_uses_committed_selected_group(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-one",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    self.remote()
    self.assertEqual(
      self.cli("test", "RED", "issue-545-one").returncode, 2,
    )
    self.assertEqual(
      self.cli("test", "GREEN", "--remote").returncode, 0,
    )
    previous = self.git("rev-parse", "HEAD^")
    self.assertEqual(
      self.git("show", "HEAD^:.ci/red-green.txt"),
      "issue-545-one",
    )
    self.assertEqual(
      (self.root / ".ci/run").read_text(),
      "GREEN-testing " + previous + "\n",
    )

  def test_remote_temporary_requires_valid_nonempty_manifest(self):
    self.remote()
    for contents in (None, "{invalid", json.dumps({
      "test-harnesses": {}, "tests": [], "aliases": {},
    })):
      with self.subTest(contents=contents):
        manifest = self.root / ".ci/temp-tests.json"
        manifest.parent.mkdir(exist_ok=True)
        if contents is None:
          manifest.unlink(missing_ok=True)
        else:
          manifest.write_text(contents)
        result = self.cli("test", "temporary", "--remote")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.source)
        self.assertFalse((self.root / ".ci/run").exists())


if __name__ == "__main__":
  unittest.main()
