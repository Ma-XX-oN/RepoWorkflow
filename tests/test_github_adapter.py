import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.github_adapter import AdapterError, github_matrix, request_changed


class GithubAdapterTests(unittest.TestCase):
  def make_repo(self):
    td = tempfile.TemporaryDirectory()
    root = Path(td.name)
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True,
                   capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root,
                   check=True)
    (root / ".ci").mkdir()
    (root / ".ci" / "run-ci-request").write_text("1.0.0-issue.1.1\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "first"], cwd=root, check=True,
                   capture_output=True)
    first = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                           capture_output=True, text=True).stdout.strip()
    (root / "other.txt").write_text("x\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "other"], cwd=root, check=True,
                   capture_output=True)
    second = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                            capture_output=True, text=True).stdout.strip()
    return td, root, first, second

  def test_manual_dispatch_requests_ci(self):
    with tempfile.TemporaryDirectory() as td:
      event = Path(td) / "event.json"
      event.write_text("{}")
      self.assertTrue(request_changed(Path(td), "workflow_dispatch", event))

  def test_push_without_request_change_does_not_request_ci(self):
    td, root, first, second = self.make_repo()
    with td:
      event = root / "event.json"
      event.write_text(json.dumps({"before": first, "after": second}))
      self.assertFalse(request_changed(root, "push", event))

  def test_push_with_request_change_requests_ci(self):
    td, root, _, second = self.make_repo()
    with td:
      before = second
      (root / ".ci" / "run-ci-request").write_text("1.0.0-issue.1.2\n")
      subprocess.run(["git", "add", "."], cwd=root, check=True)
      subprocess.run(["git", "commit", "-m", "request"], cwd=root, check=True,
                     capture_output=True)
      after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                             capture_output=True, text=True).stdout.strip()
      event = root / "event.json"
      event.write_text(json.dumps({"before": before, "after": after}))
      self.assertTrue(request_changed(root, "push", event))

  def test_new_branch_uses_event_commit_file_lists(self):
    td, root, _, second = self.make_repo()
    with td:
      event = root / "event.json"
      event.write_text(json.dumps({
        "created": True,
        "before": "0" * 40,
        "after": second,
        "commits": [{
          "added": [], "modified": [".ci/run-ci-request"], "removed": []
        }],
      }))
      self.assertTrue(request_changed(root, "push", event))

  def test_pr_event_does_not_start_expensive_ci(self):
    with tempfile.TemporaryDirectory() as td:
      event = Path(td) / "event.json"
      event.write_text("{}")
      self.assertFalse(request_changed(Path(td), "pull_request", event))

  def test_matrix_maps_every_environment_to_runner(self):
    config = {"environments": [
      {"id": "linux", "required": True},
      {"id": "windows", "required": True},
    ]}
    github = {"schema": 1, "prepareRunner": "ubuntu-latest", "runners": {
      "linux": "ubuntu-latest", "windows": "windows-latest"
    }}
    self.assertEqual(github_matrix(config, github), {"include": [
      {
        "id": "linux", "runner": "ubuntu-latest",
        "nodeVersion": "", "pythonVersion": "3.13",
      },
      {
        "id": "windows", "runner": "windows-latest",
        "nodeVersion": "", "pythonVersion": "3.13",
      },
    ]})

  def test_matrix_rejects_missing_runner_mapping(self):
    with self.assertRaises(AdapterError):
      github_matrix(
        {"environments": [{"id": "linux", "required": True}]},
        {"schema": 1, "prepareRunner": "ubuntu-latest", "runners": {}},
      )

  def test_matrix_rejects_stale_runner_mapping(self):
    with self.assertRaises(AdapterError):
      github_matrix(
        {"environments": [{"id": "linux", "required": True}]},
        {"schema": 1, "prepareRunner": "ubuntu-latest", "runners": {
          "linux": "ubuntu-latest", "old": "ubuntu-latest"
        }},
      )


if __name__ == "__main__":
  unittest.main()
