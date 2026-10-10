from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import json
import subprocess
import unittest
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[1] / "adapters"
SPEC = importlib.util.spec_from_file_location(
  "repo_host_github_reads", PATH / "repo_host_github_reads.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
SHA = "b" * 40


def result(value: object, status: int = 0):
  return SimpleNamespace(
    returncode=status,
    stdout=json.dumps(value),
    stderr="untrusted detail",
  )


class GitHubReadBoundaryTests(unittest.TestCase):

  def test_issue_normalized_and_read_only(self):
    payload = {"number": 8, "title": "Example", "state": "open"}
    with patch.object(
      MODULE.subprocess, "run", return_value=result(payload)
    ) as run:
      value = MODULE.issue_get("owner/repo", 8)
    self.assertEqual(value, payload)
    self.assertEqual(run.call_args.args[0], [
      "gh", "api", "--method", "GET", "repos/owner/repo/issues/8",
    ])

  def test_issue_rejects_pr_number_or_changed_number(self):
    values = [
      {"number": 8, "title": "Example", "state": "open",
       "pull_request": {}},
      {"number": 9, "title": "Example", "state": "open"},
      {"number": True, "title": "Example", "state": "open"},
      {"number": 8, "title": "", "state": "open"},
      {"number": 8, "title": "Example", "state": "invalid"},
    ]
    for payload in values:
      with self.subTest(payload=payload):
        with patch.object(
          MODULE.subprocess, "run", return_value=result(payload)
        ):
          with self.assertRaises(MODULE.ProviderReadError):
            MODULE.issue_get("owner/repo", 8)

  def test_pr_exact_head_destination_and_result(self):
    payload = {
      "number": 9, "head": {"sha": SHA},
      "base": {"sha": "a" * 40, "ref": "main"},
      "draft": False, "state": "open",
    }
    with patch.object(MODULE.subprocess, "run", return_value=result(payload)):
      value = MODULE.pull_request_get("owner/repo", 9)
    self.assertEqual(value["head_sha"], SHA)
    self.assertEqual(value["destination_sha"], "a" * 40)
    self.assertEqual(value["number"], 9)
    self.assertEqual(value["target_ref"], "refs/heads/main")

  def test_pr_rejects_missing_or_malformed_identity(self):
    good = {
      "number": 9, "head": {"sha": SHA},
      "base": {"sha": "a" * 40, "ref": "main"},
      "draft": False, "state": "open",
    }
    mutations = [
      {"number": 8}, {"head": {}}, {"base": {}},
      {"draft": 0}, {"state": "merged"},
      {"base": {"sha": "x", "ref": "main"}},
    ]
    for mutation in mutations:
      with self.subTest(mutation=mutation):
        payload = {**good, **mutation}
        with patch.object(
          MODULE.subprocess, "run", return_value=result(payload)
        ):
          with self.assertRaises(MODULE.ProviderReadError):
            MODULE.pull_request_get("owner/repo", 9)

  def test_branch_exact_commit_object(self):
    payload = {
      "ref": "refs/heads/work",
      "object": {"type": "commit", "sha": SHA},
    }
    with patch.object(MODULE.subprocess, "run", return_value=result(payload)):
      self.assertEqual(MODULE.branch_head("owner/repo", "work"), SHA)
    payload["ref"] = "refs/heads/other"
    with patch.object(MODULE.subprocess, "run", return_value=result(payload)):
      with self.assertRaises(MODULE.ProviderReadError):
        MODULE.branch_head("owner/repo", "work")

  def test_invalid_inputs_fail_before_subprocess(self):
    with patch.object(MODULE.subprocess, "run") as run:
      for repository in ["", "owner", "a/b/c", "../repo"]:
        with self.subTest(repository=repository):
          with self.assertRaises(MODULE.ProviderReadError):
            MODULE.issue_get(repository, 1)
      for name in ["../escape", "a//b", "/root", "", "x;cmd"]:
        with self.subTest(name=name):
          with self.assertRaises(MODULE.ProviderReadError):
            MODULE.branch_head("owner/repo", name)
      run.assert_not_called()


  def test_cli_missing_or_timeout_fails_with_safe_error(self):
    errors = [
      FileNotFoundError("executable missing"),
      subprocess.TimeoutExpired(["gh", "api"], 30),
    ]
    for failure in errors:
      with self.subTest(failure=failure):
        with patch.object(
          MODULE.subprocess, "run", side_effect=failure
        ):
          with self.assertRaises(MODULE.ProviderReadError) as caught:
            MODULE.issue_get("owner/repo", 1)
          self.assertNotIn("executable missing", str(caught.exception))
          self.assertNotIn("gh", str(caught.exception))

  def test_provider_failure_malformed_json_and_array_fail(self):
    responses = [
      result({}, status=1),
      SimpleNamespace(returncode=0, stdout="{", stderr="secret"),
      result([]),
    ]
    for response in responses:
      with self.subTest(response=response):
        with patch.object(MODULE.subprocess, "run", return_value=response):
          with self.assertRaises(MODULE.ProviderReadError) as caught:
            MODULE.issue_get("owner/repo", 1)
          self.assertNotIn("secret", str(caught.exception))


if __name__ == "__main__":
  unittest.main()
