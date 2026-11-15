from __future__ import annotations

import contextlib
import base64
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from repo_workflow.repo_info_adapter import (
  RepoInfoError, ci_invocation_status, resolve_info_config, repository_info,
)
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


class DiscoveredProviderTests(unittest.TestCase):
  def discovery(self, remotes, config=None):
    with tempfile.TemporaryDirectory() as td, patch(
      "repo_workflow.repo_info_adapter.run_command",
      side_effect=[
        SimpleNamespace(returncode=0, stdout="origin\n", stderr=""),
        SimpleNamespace(returncode=0, stdout=remotes + "\n", stderr=""),
      ],
    ):
      return resolve_info_config(Path(td), config)

  def test_unconfigured_github_selects_ci_capable_provider(self):
    result = self.discovery("https://github.com/example/consumer.git")
    command = result["infoCommand"]
    self.assertEqual(Path(command[1]).name, "repo-info-ci-github.py")
    self.assertEqual(Path(command[1]).parent.name, "adapters")
    self.assertEqual(command[-4:], [
      "--repository", "example/consumer", "--workflow", "remote-rwf.yml",
    ])

  def test_existing_explicit_provider_configuration_is_unchanged(self):
    config = {"infoCommand": [sys.executable, "fake-provider.py"]}
    with patch("repo_workflow.repo_info_adapter.run_command") as invoked:
      self.assertIs(resolve_info_config(Path("."), config), config)
    invoked.assert_not_called()

  def test_non_github_does_not_silently_select_github(self):
    with self.assertRaisesRegex(RepoInfoError, "no GitHub remote"):
      self.discovery("https://gitlab.com/example/consumer.git")
    with patch("repo_workflow.repo_info_adapter.run_command") as invoked:
      config = {"infoCommand": ["provider-neutral-command"]}
      self.assertIs(resolve_info_config(Path("."), config), config)
    invoked.assert_not_called()

  def test_unconfigured_provider_not_supported_is_explicit_failure(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      RepoFixture(root)
      with self.assertRaisesRegex(RepoInfoError, "not configured"):
        ci_invocation_status(root, {}, BRANCH, SHA, 2)

  def test_discovered_provider_reports_missing_credentials_and_api_failure(self):
    config = self.discovery("git@github.com:example/consumer.git")
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      RepoFixture(root)
      for diagnostic in ("authentication required", "HTTP 403"):
        with self.subTest(diagnostic=diagnostic), patch(
          "repo_workflow.repo_info_adapter.run_command",
          return_value=SimpleNamespace(
            returncode=2, stdout="", stderr=diagnostic,
          ),
        ):
          # Provider errors must never become an empty/not-observed success.
          with self.assertRaisesRegex(RepoInfoError, diagnostic):
            ci_invocation_status(root, config, BRANCH, SHA, 2)

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
    total = sum(len(page["workflow_runs"]) for page in pages)
    pages = [{"total_count": total, **page} for page in pages]
    output = io.StringIO()
    with patch.object(PROVIDER, "verify_request_marker"), patch.object(
      PROVIDER, "gh_json", side_effect=pages
    ) as gh, contextlib.redirect_stdout(output):
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
    full_page = {"total_count": 10000, "workflow_runs": [
      github_run("completed", run_id=i + 1, head_sha="b" * 40)
      for i in range(100)
    ]}
    with patch.object(PROVIDER, "verify_request_marker"), patch.object(
      PROVIDER, "gh_json", return_value=full_page
    ) as gh:
      with self.assertRaisesRegex(SystemExit, "2"):
        PROVIDER.status("o/r", "remote.yml", BRANCH, SHA, 2)
    self.assertEqual(gh.call_count, 100)

  def test_provider_pagination_count_mismatch_fails_closed(self):
    wrong = {"total_count": 2, "workflow_runs": [github_run("completed")]}
    with patch.object(PROVIDER, "verify_request_marker"), patch.object(
      PROVIDER, "gh_json", return_value=wrong
    ):
      with self.assertRaises(SystemExit):
        PROVIDER.status("o/r", "remote.yml", BRANCH, SHA, 2)
    bad = {"total_count": "not-an-int", "workflow_runs": []}
    with patch.object(PROVIDER, "verify_request_marker"), patch.object(
      PROVIDER, "gh_json", return_value=bad
    ):
      with self.assertRaises(SystemExit):
        PROVIDER.status("o/r", "remote.yml", BRANCH, SHA, 2)

  def test_invalid_provider_responses_fail_closed(self):
    for malformed in (
      {}, {"workflow_runs": None}, {"workflow_runs": []},
      {"total_count": 1, "workflow_runs": [None]},
      {"total_count": 1, "workflow_runs": [github_run("completed", run_id=False)]},
    ):
      with self.subTest(malformed=malformed), patch.object(
        PROVIDER, "gh_json", return_value=malformed
      ), patch.object(PROVIDER, "verify_request_marker"), self.assertRaises(SystemExit):
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

  def test_committed_request_marker_exact_retry_binding(self):
    def response(value):
      return {
        "type": "file", "encoding": "base64",
        "content": base64.b64encode(value).decode("ascii"),
      }
    valid = response(b"test RED --remote 2\n")
    with patch.object(PROVIDER, "gh_json", return_value=valid) as fetch:
      PROVIDER.verify_request_marker("o/r", SHA, 2)
    self.assertIn("/contents/.ci/rwf?ref=" + SHA, fetch.call_args.args[0])
    invalid = [
      response(b"test RED --remote 1\n"),
      response(b"test RED --remote 20\n"),
      response(b"test RED --remote -1\n"),
      response(b"test RED --remote not-an-attempt\n"),
      response(b"test RED --remote 2\nother"),
      response(b"test RED --remote 2\x00"),
      response(b"--remote 2"),
      {"type": "file", "encoding": "base64", "content": "!!!"},
      response(b"\xff"),
      {"type": "dir", "encoding": "base64", "content": valid["content"]},
      {"type": "file", "encoding": "base64", "content": None},
    ]
    for payload in invalid:
      with self.subTest(payload=payload), patch.object(
        PROVIDER, "gh_json", return_value=payload
      ), self.assertRaises(SystemExit):
        PROVIDER.verify_request_marker("o/r", SHA, 2)

  def test_adapter_entrypoint_uses_shared_utf8_boundary(self):
    import runpy
    from repo_workflow.output import configure_utf8_output
    with patch("repo_workflow.output.configure_utf8_output", return_value=False) as init:
      with patch.object(sys, "argv", [str(SCRIPT), "--repository", "o/r", "repository"]):
        with self.assertRaises(SystemExit) as stopped:
          runpy.run_path(str(SCRIPT), run_name="__main__")
    self.assertEqual(stopped.exception.code, 2)
    init.assert_called_once()

  def test_adapter_fails_closed_on_unconfigurable_output_before_dispatch(self):
    import runpy
    class UnsupportedStream:
      encoding = "cp1252"
      errors = "strict"
      closed = False

      def write(self, text):
        raise AssertionError("must not emit through incompatible output")

    with patch.object(sys, "stdout", UnsupportedStream()):
      with patch.object(sys, "argv", [str(SCRIPT), "--repository", "o/r", "repository"]):
        with self.assertRaises(SystemExit) as stopped:
          runpy.run_path(str(SCRIPT), run_name="__main__")
    self.assertEqual(stopped.exception.code, 2)

  def test_status_rejects_attempt_mismatch_before_workflow_lookup(self):
    payload = {
      "type": "file", "encoding": "base64",
      "content": base64.b64encode(b"test GREEN --remote 1\n").decode("ascii"),
    }
    with patch.object(PROVIDER, "gh_json", return_value=payload) as fetch:
      with self.assertRaises(SystemExit):
        PROVIDER.status("o/r", "remote.yml", BRANCH, SHA, 2)
    fetch.assert_called_once()

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
