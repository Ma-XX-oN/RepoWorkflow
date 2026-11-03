from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from repo_workflow.repo_info_adapter import RepoInfoError, ci_invocation_status
from tests.support import RepoFixture


SHA = "a" * 40
BRANCH = "CMD-7-issue-792"
SCRIPT = Path(__file__).resolve().parents[1] / "adapters" / "repo-info-ci-github.py"
SPEC = importlib.util.spec_from_file_location("rwf_ci_github", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
PROVIDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROVIDER)


def run_payload(state, run_id=None, detail=None, **changes):
  result = {
    "schema_version": 1,
    "branch": BRANCH,
    "request_revision": SHA,
    "attempt": 2,
    "state": state,
    "run_id": run_id,
    "detail": detail,
  }
  result.update(changes)
  return result


def github_run(status, run_id=11, **changes):
  result = {
    "id": run_id,
    "head_sha": SHA,
    "head_branch": BRANCH,
    "event": "push",
    "status": status,
  }
  result.update(changes)
  return result


class CoreStatusTests(unittest.TestCase):
  def read(self, payload):
    with patch("repo_workflow.repo_info_adapter._invoke", return_value=payload) as invoked:
      result = ci_invocation_status(Path("."), {}, BRANCH, SHA.upper(), 2)
    invoked.assert_called_once_with(
      Path("."), {}, ["ci", "invocation", "status", BRANCH, SHA, "2"]
    )
    return result

  def test_all_normalized_states_and_identity(self):
    for state in ("queued", "running", "completed", "not-observed", "unknown"):
      with self.subTest(state=state):
        payload = run_payload(
          state,
          None if state in ("unknown", "not-observed") else 123,
          "unclassified" if state == "unknown" else None,
        )
        self.assertEqual(self.read(payload), payload)

  def test_untrusted_normalized_results_fail_closed(self):
    invalid = [
      {"branch": "CMD-8-other"},
      {"request_revision": "b" * 40},
      {"attempt": 1},
      {"attempt": True},
      {"schema_version": 2},
      {"state": "success"},
      {"state": []},
      {"state": "completed", "run_id": None},
      {"run_id": 0},
      {"run_id": True},
      {"state": "not-observed", "run_id": 7},
      {"state": "unknown", "detail": None},
      {"state": "completed", "detail": 42},
      {"state": "completed", "detail": "unexpected"},
      {"unexpected": "raw provider payload"},
    ]
    for change in invalid:
      with self.subTest(change=change), patch(
        "repo_workflow.repo_info_adapter._invoke",
        return_value={**run_payload("queued", 1), **change},
      ):
        with self.assertRaises(RepoInfoError):
          ci_invocation_status(Path("."), {}, BRANCH, SHA, 2)

  def test_invalid_client_request_fails_without_provider_invocation(self):
    invalid = [
      ("issue-792", SHA, 2),
      ("CMD-0-bad", SHA, 2),
      ("CMD-7-bad\n", SHA, 2),
      (BRANCH, "abc", 2),
      (BRANCH, SHA, -1),
      (BRANCH, SHA, True),
    ]
    with patch("repo_workflow.repo_info_adapter._invoke") as invoked:
      for args in invalid:
        with self.subTest(args=args), self.assertRaises(RepoInfoError):
          ci_invocation_status(Path("."), {}, *args)
    invoked.assert_not_called()

  def test_configured_fake_provider_through_real_read_only_dispatch(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)
      script = root / "fake_info.py"
      payload = run_payload("completed", 135)
      script.write_text(
        "import json, sys\n"
        + "assert sys.argv[1:] == " +
        repr(["ci", "invocation", "status", BRANCH, SHA, "2"]) + "\n"
        + "print(" + repr(json.dumps(payload)) + ")\n",
        encoding="utf-8",
      )
      config = {"infoCommand": [sys.executable, str(script)]}
      self.assertEqual(
        ci_invocation_status(root, config, BRANCH, SHA, 2), payload
      )

  def test_adapter_errors_are_not_not_observed(self):
    with patch(
      "repo_workflow.repo_info_adapter._invoke",
      side_effect=RepoInfoError("credentials unavailable"),
    ):
      with self.assertRaisesRegex(RepoInfoError, "credentials"):
        ci_invocation_status(Path("."), {}, BRANCH, SHA, 2)


class GithubStatusTests(unittest.TestCase):
  def lookup(self, pages):
    output = io.StringIO()
    with patch.object(PROVIDER, "gh_json", side_effect=pages) as gh, contextlib.redirect_stdout(output):
      PROVIDER.status("Ma-XX-oN/RepoWorkflow", "remote-rwf.yml", BRANCH, SHA, 2)
    value = json.loads(output.getvalue())
    self.assertEqual(value["branch"], BRANCH)
    self.assertEqual(value["request_revision"], SHA)
    self.assertEqual(value["attempt"], 2)
    return value, gh

  def test_five_states(self):
    cases = [
      ("requested", "queued"), ("queued", "queued"),
      ("waiting", "queued"), ("pending", "queued"),
      ("in_progress", "running"), ("completed", "completed"),
      ("mystery", "unknown"),
    ]
    for provider_state, expected in cases:
      with self.subTest(provider_state=provider_state):
        result, _ = self.lookup([{"workflow_runs": [github_run(provider_state)]}])
        self.assertEqual(result["state"], expected)
        self.assertEqual(result["run_id"], 11)

  def test_missing_and_stale_runs_are_not_observed_not_safe_to_retry(self):
    result, _ = self.lookup([{"workflow_runs": [
      github_run("completed", head_sha="b" * 40),
      github_run("completed", head_branch="CMD-8-other", run_id=12),
      github_run("completed", event="workflow_dispatch", run_id=13),
    ]}])
    self.assertEqual(result["state"], "not-observed")
    self.assertIsNone(result["run_id"])

  def test_duplicate_exact_request_runs_fail_closed_as_unknown(self):
    result, _ = self.lookup([{"workflow_runs": [
      github_run("completed", 11), github_run("in_progress", 12),
    ]}])
    self.assertEqual(result["state"], "unknown")
    self.assertIsNone(result["run_id"])

  def test_pagination_and_exact_query_binding(self):
    first = [github_run("completed", run_id=i + 1, head_sha="b" * 40)
             for i in range(100)]
    result, gh = self.lookup([
      {"workflow_runs": first},
      {"workflow_runs": [github_run("in_progress", 101)]},
    ])
    self.assertEqual(result["state"], "running")
    self.assertEqual(gh.call_count, 2)
    for call in gh.call_args_list:
      endpoint = call.args[0]
      self.assertIn("head_sha=" + SHA, endpoint)
      self.assertIn("branch=CMD-7-issue-792", endpoint)
      self.assertIn("event=push", endpoint)
      self.assertIn("remote-rwf.yml", endpoint)

  def test_non_exhaustive_pagination_fails_closed(self):
    full_page = {"workflow_runs": [
      github_run("completed", run_id=i + 1, head_sha="b" * 40)
      for i in range(100)
    ]}
    with patch.object(PROVIDER, "gh_json", return_value=full_page) as gh:
      with self.assertRaisesRegex(SystemExit, "2"):
        PROVIDER.status("o/r", "remote.yml", BRANCH, SHA, 2)
    self.assertEqual(gh.call_count, 100)

  def test_invalid_provider_responses_fail_closed(self):
    for malformed in ({}, {"workflow_runs": None}, {"workflow_runs": [None]},
                      {"workflow_runs": [github_run("completed", run_id=False)]}):
      with self.subTest(malformed=malformed), patch.object(
        PROVIDER, "gh_json", return_value=malformed
      ), self.assertRaises(SystemExit):
        PROVIDER.status("o/r", "remote-rwf.yml", BRANCH, SHA, 2)

  def test_failed_credentials_malformed_json_and_unicode_fail(self):
    cases = [
      subprocess.CompletedProcess([], 1, b"", b"credentials unavailable"),
      subprocess.CompletedProcess([], 0, b"not-json", b""),
      subprocess.CompletedProcess([], 0, b"\xff", b""),
    ]
    for case in cases:
      with self.subTest(code=case.returncode, stdout=case.stdout), patch.object(
        PROVIDER.subprocess, "run", return_value=case
      ), self.assertRaises(SystemExit):
        PROVIDER.gh_json("repos/o/r/actions/workflows/w/runs")
    with patch.object(PROVIDER.subprocess, "run", side_effect=FileNotFoundError("gh")):
      with self.assertRaises(SystemExit):
        PROVIDER.gh_json("repos/o/r/actions/workflows/w/runs")

  def test_invalid_arguments_fail_before_provider_call(self):
    invalid = [
      ("o/r", "../bad.yml", BRANCH, SHA, 2),
      ("o/r", "remote.yml", "not-cmd", SHA, 2),
      ("o/r", "remote.yml", BRANCH, SHA, -1),
      ("o/r", "remote.yml", BRANCH, "bad", 2),
    ]
    with patch.object(PROVIDER, "gh_json") as gh:
      for args in invalid:
        with self.subTest(args=args), self.assertRaises(SystemExit):
          PROVIDER.status(*args)
    gh.assert_not_called()

  def test_existing_operations_delegate_to_original_provider(self):
    with patch.object(PROVIDER.subprocess, "call", return_value=0) as delegated:
      self.assertEqual(PROVIDER.main([
        "--repository", "o/r", "--workflow", "remote.yml", "issue", "list-open",
      ]), 0)
    arguments = delegated.call_args.args[0]
    self.assertTrue(arguments[1].endswith("repo-info-github.py"))
    self.assertEqual(arguments[-2:], ["issue", "list-open"])

  def test_required_workflow_is_not_inferred(self):
    with patch.object(PROVIDER, "gh_json") as gh:
      with self.assertRaises(SystemExit):
        PROVIDER.main([
          "--repository", "o/r", "ci", "invocation",
          "status", BRANCH, SHA, "2",
        ])
    gh.assert_not_called()


if __name__ == "__main__":
  unittest.main()
