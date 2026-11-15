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

  def test_invalid_remote_placement_refused_before_side_effects(self):
    self.remote()
    before = self.git("rev-parse", "HEAD")
    for stage in (
      "RED", "temporary", "GREEN", "regression",
      "integration", "results",
    ):
      with self.subTest(stage=stage):
        output = self.cli("test", "--remote", stage)
        self.assertEqual(output.returncode, 2)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertFalse((self.root / ".ci/run").exists())


  def test_remote_request_reuses_cmd_without_mutating_source(self):
    bare = self.remote()
    previous = self.git("rev-parse", "HEAD")
    first = self.cli("test", "regression", "--remote")
    self.assertEqual(first.returncode, 0, first.stderr)
    self.assertIn("CMD-1-issue-545-fixture SUBMITTED", first.stdout)
    second = self.cli("test", "regression", "--remote")
    self.assertEqual(second.returncode, 0, second.stderr)
    self.assertIn("CMD-1-issue-545-fixture REUSED", second.stdout)
    self.assertEqual(self.git("rev-parse", "HEAD"), previous)
    self.assertFalse((self.root / ".ci/run").exists())
    request = subprocess.run(
      ["git", "--git-dir", str(bare), "rev-parse",
       "refs/heads/CMD-1-issue-545-fixture"],
      text=True, capture_output=True, check=True,
    ).stdout.strip()
    self.assertEqual(self.git("rev-parse", request + "^"), previous)
    self.assertEqual(
      self.git("diff-tree", "--no-commit-id", "--name-only", "-r", request),
      ".ci/rwf",
    )
    self.assertEqual(self.git("show", request + ":.ci/rwf"),
                     "test regression --remote 0")

  def test_dirty_tree_is_preserved_and_request_uses_committed_tip(self):
    bare = self.remote()
    (self.root / "README").write_text("edited\n")
    status_before = self.git("status", "--porcelain")
    result = self.cli("test", "regression", "--remote")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(self.git("rev-parse", "HEAD"), self.source)
    self.assertEqual(self.git("status", "--porcelain"), status_before)
    self.assertEqual((self.root / "README").read_text(), "edited\n")
    self.assertEqual(
      subprocess.run(
        ["git", "--git-dir", str(bare), "rev-parse",
         "refs/heads/CMD-1-issue-545-fixture^"],
        text=True, capture_output=True, check=True,
      ).stdout.strip(), self.source,
    )

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

  def test_remote_results_reject_malformed_evidence_atomically(self):
    self.remote()
    path = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    path.parent.mkdir(parents=True)
    valid = {
      "testSHA": self.source, "kind": "GREEN",
      "result": "succeeded", "runner": "github-actions",
    }
    bad = (
      '{"testSHA":"' + self.source
      + '","kind":"GREEN","result":"succeeded",'
      + '"runner":"github-actions","metrics":{"elapsed":1e999}}'
    )
    path.write_text(json.dumps(valid) + "\n" + bad + "\n")
    self.git("add", ".repoworkflow/validation/testResults-545.jsonl")
    self.git("commit", "-m", "publish malformed remote log")
    self.git("push")
    path.unlink()
    before = self.git("rev-parse", "HEAD")
    output = self.cli("test", "results", "--remote")
    self.assertEqual(output.returncode, 2)
    self.assertEqual(output.stdout, "")
    self.assertIn("nonfinite testing log value", output.stderr)
    self.assertEqual(self.git("rev-parse", "HEAD"), before)


  def test_remote_green_uses_committed_selected_group(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-one",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    bare = self.remote()
    self.assertEqual(
      self.cli("test", "RED", "issue-545-one").returncode, 2,
    )
    self.assertEqual(self.git("show", "HEAD:.ci/red-green.txt"),
                     "issue-545-one")
    previous = self.git("rev-parse", "HEAD")
    remote = self.cli("test", "GREEN", "--remote")
    self.assertEqual(remote.returncode, 0, remote.stderr)
    self.assertEqual(self.git("rev-parse", "HEAD"), previous)
    request = subprocess.run(
      ["git", "--git-dir", str(bare), "rev-parse",
       "refs/heads/CMD-1-issue-545-fixture"],
      text=True, capture_output=True, check=True,
    ).stdout.strip()
    self.assertEqual(self.git("rev-parse", request + "^"), previous)
    self.assertEqual(self.git("show", request + ":.ci/rwf"),
                     "test GREEN --remote 0")

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
