"""#790: status selection, pending, completion and provider failure tests."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from io import StringIO

from repo_workflow.remote_result import PublishedResult
from repo_workflow.remote_request import SubmittedRequest
from repo_workflow.remote_status import (
  PENDING_EXIT, CommandStatus, RemoteStatusError, submit_remote,
  parse_intervals, remote_status, resolve_command, command_status,
)


def git(root, *args):
  completed = subprocess.run(
    ["git", *args], cwd=root, capture_output=True, check=True,
  )
  return completed.stdout.decode("utf-8", "strict").strip()


class StatusTest(unittest.TestCase):
  def setUp(self):
    temp = tempfile.TemporaryDirectory()
    self.addCleanup(temp.cleanup)
    self.root = Path(temp.name)
    git(self.root, "init", "--bare", str(self.root / "remote.git"))
    git(self.root, "init", "-b", "issue-790")
    git(self.root, "config", "user.name", "tester")
    git(self.root, "config", "user.email", "tester@example.invalid")
    git(self.root, "remote", "add", "origin", str(self.root / "remote.git"))
    (self.root / "README").write_text("ok\n", encoding="utf-8")
    git(self.root, "add", "README")
    git(self.root, "commit", "-m", "source")

  def add_cmd(self, number):
    branch = f"CMD-{number}-issue-790"
    git(self.root, "checkout", "-b", branch, "issue-790")
    (self.root / ".ci").mkdir(exist_ok=True)
    (self.root / ".ci/rwf").write_text(
      "test RED --remote 0\n", encoding="utf-8",
    )
    git(self.root, "add", ".ci/rwf")
    git(self.root, "commit", "-m", "request",
        "-m", f"RWF-Source: {git(self.root, 'rev-parse', 'issue-790')}")
    git(self.root, "push", "origin", branch)
    git(self.root, "checkout", "issue-790")
    return branch

  def test_default_explicit_and_negative_selection(self):
    self.add_cmd(2)
    self.add_cmd(7)
    self.assertEqual(resolve_command(self.root).number, 7)
    self.assertEqual(resolve_command(self.root, -1).number, 7)
    self.assertEqual(resolve_command(self.root, -2).number, 2)
    self.assertEqual(resolve_command(self.root, 2).number, 2)
    for value in (0, 1, 8, -3):
      with self.subTest(value=value), self.assertRaises(RemoteStatusError):
        resolve_command(self.root, value)

  def test_unobserved_is_pending_never_retry(self):
    self.add_cmd(1)
    with patch("repo_workflow.remote_status.ci_invocation_status",
               return_value={"state": "not-observed", "run_id": None}):
      with patch("repo_workflow.remote_status.read_result", return_value=None):
        with patch("repo_workflow.remote_status._marker",
                   return_value=("a" * 40, 0)):
          with patch("repo_workflow.remote_status._tip_unchanged"):
            self.assertEqual(command_status(
              self.root, info_config={"infoCommand": ["fake"]},
            ).state, "not-observed")

  def test_completed_code_and_output_preserved(self):
    result = PublishedResult("CMD-1-issue-790", "a" * 40,
                             0, 75, "λ failed\n", "b" * 40)
    status = CommandStatus(1, result.branch, result.request_sha,
                           0, "completed", result, None)
    with patch("repo_workflow.remote_status.command_status",
               return_value=status):
      self.assertEqual(remote_status(self.root), 75)

  def test_utf8_output_does_not_inherit_legacy_console_code_page(self):
    # Deliberately simulate a CP1252 stdout even on POSIX platforms.
    # A return-code-only assertion cannot detect lost Unicode output.
    from io import BytesIO, TextIOWrapper
    from repo_workflow.remote_status import _render
    result = PublishedResult("CMD-1-issue-790", "a" * 40,
                             0, 9, "λ failed\n", "b" * 40)
    status = CommandStatus(1, result.branch, result.request_sha,
                           0, "completed", result, None)
    raw = BytesIO()
    console = TextIOWrapper(raw, encoding="cp1252", errors="strict")
    with patch("repo_workflow.remote_status.sys.stdout", console):
      self.assertEqual(_render(status), 9)
      console.flush()
    self.assertEqual(
      raw.getvalue().decode("utf-8", "strict"),
      "CMD-1 CMD-1-issue-790 COMPLETED exit=9\nλ failed\n",
    )

  def test_submitted_cmd_output_is_strict_utf8_lf_under_cp1252(self):
    # A request's Unicode branch name and an error both cross CLI text I/O.
    from io import BytesIO, TextIOWrapper
    from repo_workflow.remote_request import RemoteRequestError

    out_bytes, err_bytes = BytesIO(), BytesIO()
    out = TextIOWrapper(out_bytes, encoding="cp1252", errors="strict")
    err = TextIOWrapper(err_bytes, encoding="cp1252", errors="strict")
    request = SubmittedRequest(1, "CMD-1-issue-λ",
                               "a" * 40, "b" * 40, False)
    with patch("repo_workflow.remote_status.sys.stdout", out):
      with patch("repo_workflow.remote_status.sys.stderr", err):
        with patch("repo_workflow.remote_status.submit_request",
                   return_value=request):
          self.assertEqual(
            submit_remote(self.root, ["test", "RED", "--remote"]), 0,
          )
        with patch("repo_workflow.remote_status.submit_request",
                   side_effect=RemoteRequestError("rejected λ")):
          self.assertEqual(
            submit_remote(self.root, ["test", "RED", "--remote"]), 1,
          )
        out.flush()
        err.flush()
    self.assertEqual(
      out_bytes.getvalue().decode("utf-8", "strict"),
      "CMD-1 CMD-1-issue-λ SUBMITTED\n",
    )
    self.assertEqual(
      err_bytes.getvalue().decode("utf-8", "strict"),
      "Remote request rejected: rejected λ\n",
    )

  def test_unconfigured_consumer_status_uses_discovered_info_adapter(self):
    from repo_workflow.repo_info_adapter import RepoInfoError
    self.add_cmd(1)
    self.assertFalse((self.root / ".ci/repoworkflow.json").exists())
    config = {"infoCommand": ["fake-provider"]}
    with patch("repo_workflow.remote_status.resolve_info_config",
               return_value=config) as resolver:
      with patch("repo_workflow.remote_status.ci_invocation_status",
                 return_value={"state": "not-observed", "run_id": None}) as query:
        status = command_status(self.root)
      resolver.assert_called_once_with(self.root)
      self.assertEqual(query.call_args.args[1], config)
      self.assertEqual(status.state, "not-observed")
      self.assertIsNone(status.result)
    with patch("repo_workflow.remote_status.resolve_info_config",
               side_effect=RepoInfoError("provider unavailable")):
      with self.assertRaisesRegex(RemoteStatusError, "provider unavailable"):
        command_status(self.root)

  def test_unconfigured_github_discovery_integrates_with_command_status(self):
    import sys
    self.add_cmd(1)
    git(self.root, "remote", "add", "github",
        "git@github.com:Ma-XX-oN/Disposable-001.git")
    self.assertFalse((self.root / ".ci/repoworkflow.json").exists())
    with patch("repo_workflow.remote_status.ci_invocation_status",
               return_value={"state": "not-observed", "run_id": None}) as query:
      status = command_status(self.root)
    self.assertEqual(status.state, "not-observed")
    self.assertIsNone(status.result)
    self.assertEqual(status.branch, "CMD-1-issue-790")
    self.assertEqual(status.retry, 0)
    self.assertEqual(query.call_count, 1)
    root, config, branch, request_sha, retry = query.call_args.args
    self.assertEqual(root, self.root)
    self.assertEqual(branch, status.branch)
    self.assertEqual(request_sha, status.request_sha)
    self.assertEqual(retry, 0)
    argv = config["infoCommand"]
    self.assertEqual(argv[0], sys.executable)
    self.assertTrue(argv[1].endswith("adapters/repo-info-ci-github.py"))
    self.assertEqual(argv[2:], [
      "--repository", "Ma-XX-oN/Disposable-001",
      "--workflow", "remote-rwf.yml",
    ])

  def test_unconfigured_reuse_before_and_after_threshold_is_safe(self):
    from repo_workflow.remote_request import submit_request
    from repo_workflow.repo_info_adapter import RepoInfoError
    self.add_cmd(1)
    self.assertFalse((self.root / ".ci/repoworkflow.json").exists())
    branch = "CMD-1-issue-790"
    marker = git(self.root, "rev-parse", branch)
    stamp = int(git(self.root, "show", "-s", "--format=%ct", marker))
    argv = ["test", "RED", "--remote"]
    before = git(self.root, "rev-parse", "HEAD")
    with patch("repo_workflow.remote_status.resolve_info_config",
               return_value={"infoCommand": ["fake"]}) as resolver:
      with patch("repo_workflow.remote_status.ci_invocation_status",
                 return_value={"state": "unknown", "run_id": None}) as query:
        self.assertEqual(submit_remote(
          self.root, argv, clock=lambda: stamp + 14,
        ), 0)
        query.assert_not_called()
        self.assertEqual(submit_remote(
          self.root, argv, clock=lambda: stamp + 15,
        ), 0)
        query.assert_called_once()
        resolver.assert_called_once_with(self.root)
    self.assertEqual(git(self.root, "rev-parse", "HEAD"), before)
    self.assertEqual(git(self.root, "ls-remote", "origin",
                         f"refs/heads/{branch}").split()[0], marker)
    with patch("repo_workflow.remote_status.resolve_info_config",
               side_effect=RepoInfoError("provider offline")):
      self.assertEqual(submit_remote(
        self.root, argv, clock=lambda: stamp + 16,
      ), 0)
    from repo_workflow.config import ConfigError
    with patch("repo_workflow.remote_status.resolve_info_config",
               side_effect=ConfigError("malformed consumer configuration")):
      self.assertEqual(submit_remote(
        self.root, argv, clock=lambda: stamp + 17,
      ), 0)
    self.assertEqual(git(self.root, "ls-remote", "origin",
                         f"refs/heads/{branch}").split()[0], marker)
    self.assertEqual(git(self.root, "rev-parse", "HEAD"), before)

  def test_named_red_remote_poll_real_cli_and_negative_paths(self):
    import json
    import sys
    from repo_workflow.remote_request import submit_request
    from repo_workflow.test_cli import select_group
    group = "issue-790-composite"
    (self.root / ".ci").mkdir(exist_ok=True)
    (self.root / "smoke_case.py").write_text(
      "import unittest\nclass Smoke(unittest.TestCase):\n"
      "  def test_red(self): self.fail('expected')\n", encoding="utf-8",
    )
    (self.root / ".ci/tests.json").write_text(json.dumps({
      "test-harnesses": {
        "unittest": {"command": "python", "layout": ["-m", "unittest", "$test"]},
      },
      "tests": [{"test-harness": "unittest", group: {
        "type": "regression", "name": "smoke_case",
        "expected-red": {"exit-code": 1, "output-contains": "expected"},
      }}],
      "aliases": {},
    }), encoding="utf-8")
    git(self.root, "add", ".ci/tests.json", "smoke_case.py")
    git(self.root, "commit", "-m", "register composite RED")
    # The test-only bare remote lives inside this fixture's work directory.
    # Ignore its bookkeeping without weakening production cleanliness checks.
    with (self.root / ".git/info/exclude").open(
      "a", encoding="utf-8",
    ) as exclusions:
      exclusions.write("\nremote.git/\n")
    select_group(self.root, group)
    before = git(self.root, "rev-parse", "HEAD")
    request = submit_request(
      self.root, ["test", "RED", group, "--remote"],
    )
    self.assertFalse(request.reused)
    git(self.root, "checkout", "-b", request.branch, request.request_sha)
    (self.root / ".repoworkflow").mkdir(exist_ok=True)
    (self.root / ".repoworkflow/result").write_text(
      "7\nλ done\n", encoding="utf-8",
    )
    git(self.root, "add", ".repoworkflow/result")
    git(self.root, "commit", "-m", "publish result",
        "-m", f"RWF-Request: {request.request_sha}\nRWF-Retry: 0")
    git(self.root, "push", "origin", f"HEAD:refs/heads/{request.branch}")
    git(self.root, "checkout", "issue-790")
    script = Path(__file__).resolve().parents[1] / "repo_workflow.py"
    args = [sys.executable, str(script), "--root", str(self.root)]
    result = subprocess.run([
      *args, "test", "RED", group, "--remote", "--poll", "0",
    ], capture_output=True, encoding="utf-8", errors="strict", check=False)
    self.assertEqual(result.returncode, 7, result.stderr)
    self.assertIn(f"CMD-1 {request.branch} REUSED", result.stdout)
    self.assertIn(f"CMD-1 {request.branch} COMPLETED exit=7", result.stdout)
    self.assertIn("λ done", result.stdout)
    for suffix in (
      ["test", "RED", "issue-790-unknown", "--remote", "--poll", "0"],
      ["test", "RED", group, "--remote", "--poll", "-1"],
      ["test", "RED", group, "--poll", "0", "--remote"],
    ):
      with self.subTest(suffix=suffix):
        invalid = subprocess.run(
          [*args, *suffix], capture_output=True, encoding="utf-8",
          errors="strict", check=False,
        )
        self.assertNotEqual(invalid.returncode, 0)
        self.assertNotIn("COMPLETED exit=", invalid.stdout)
    self.assertEqual(git(self.root, "rev-parse", "HEAD"), before)
    self.assertFalse((self.root / ".ci/run").exists())

  def test_poll_repeats_last_interval_and_never_submits(self):
    pending = CommandStatus(1, "CMD-1-issue-790", "a" * 40,
                            0, "running", None, 123)
    done = replace(pending, state="completed",
                   result=PublishedResult(
                     pending.branch, pending.request_sha, 0,
                     9, "failed\n", "b" * 40,
                   ))
    sleeps = []
    with patch("repo_workflow.remote_status.command_status",
               side_effect=[pending, pending, pending, done]):
      self.assertEqual(remote_status(
        self.root, intervals=(0.0, 0.1), sleep=sleeps.append,
      ), 9)
    self.assertEqual(sleeps, [0.0, 0.1, 0.1])

  def test_poll_intervals_reject_malformed(self):
    self.assertEqual(parse_intervals([]), (15.0,))
    self.assertIsNone(parse_intervals(None))
    for values in (["-1"], ["nan"], ["inf"], ["1e3"],
                   ["86401"], ["+1"], ["1", "bad"]):
      with self.subTest(values=values), self.assertRaises(RemoteStatusError):
        parse_intervals(values)

  def test_provider_errors_fail_closed(self):
    self.add_cmd(1)
    with patch("repo_workflow.remote_status.read_result", return_value=None):
      with patch("repo_workflow.remote_status._marker",
                 return_value=("a" * 40, 0)):
        with patch("repo_workflow.remote_status.ci_invocation_status",
                   side_effect=Exception("provider unavailable")):
          with self.assertRaises(Exception):
            command_status(
              self.root, info_config={"infoCommand": ["fake"]},
            )


  def test_cli_grammar_status_and_poll(self):
    from repo_workflow.command_grammar import Context, parse_tokens
    from repo_workflow.public_commands import COMMANDS
    context = Context(self.root, legal_only=False)
    for words in (
      ["remote-status"],
      ["remote-status", "2"],
      ["remote-status", "-1"],
      ["remote-status", "--poll"],
      ["remote-status", "-1", "--poll", "0", "0.1"],
      ["test", "RED", "--remote", "--poll", "0"],
    ):
      with self.subTest(words=words):
        self.assertEqual(
          parse_tokens(COMMANDS, context, words), tuple(words),
        )

  def test_one_shot_pending_exit_is_distinctly_labeled(self):
    pending = CommandStatus(2, "CMD-2-issue-790",
                            "a" * 40, 0, "running", None, 123)
    output = StringIO()
    with patch("repo_workflow.remote_status.command_status",
               return_value=pending), redirect_stdout(output):
      self.assertEqual(remote_status(self.root), PENDING_EXIT)
    self.assertIn("CMD-2 CMD-2-issue-790 PENDING (running)", output.getvalue())

  def test_submission_reuses_idempotently_without_retry_before_threshold(self):
    req = SubmittedRequest(2, "CMD-2-issue-790",
                           "b" * 40, "a" * 40, True)
    with patch("repo_workflow.remote_status.submit_request",
               return_value=req) as submit:
      with patch("repo_workflow.remote_status._git", return_value="100"):
        with patch("repo_workflow.remote_status.command_status") as status:
          self.assertEqual(submit_remote(
            self.root, ["test", "RED", "--remote"], clock=lambda: 114,
          ), 0)
          status.assert_not_called()
      submit.assert_called_once()

  def test_reuse_after_threshold_queries_provider_without_retry(self):
    req = SubmittedRequest(2, "CMD-2-issue-790",
                           "b" * 40, "a" * 40, True)
    pending = CommandStatus(2, req.branch, req.request_sha,
                            0, "unknown", None, None)
    with patch("repo_workflow.remote_status.submit_request",
               return_value=req) as submit:
      with patch("repo_workflow.remote_status._git", return_value="100"):
        observer = lambda *args, **kwargs: pending
        self.assertEqual(submit_remote(
          self.root, ["test", "RED", "--remote"],
          clock=lambda: 115, status_reader=observer,
        ), 0)
      submit.assert_called_once()

  def test_submission_failure_returns_one(self):
    from repo_workflow.remote_request import RemoteRequestError
    with patch("repo_workflow.remote_status.submit_request",
               side_effect=RemoteRequestError("rejected")):
      self.assertEqual(submit_remote(
        self.root, ["test", "RED", "--remote"],
      ), 1)

  def test_polled_submission_checks_original_request_identity(self):
    req = SubmittedRequest(2, "CMD-2-issue-790",
                           "b" * 40, "a" * 40, False)
    with patch("repo_workflow.remote_status.submit_request",
               return_value=req):
      with patch("repo_workflow.remote_status.remote_status",
                 return_value=4) as status:
        self.assertEqual(submit_remote(
          self.root, ["test", "RED", "--remote"], intervals=(0.0,),
        ), 4)
        self.assertEqual(status.call_args.kwargs["expected_request"],
                         req.request_sha)

  def test_cli_status_does_not_configure_merge_driver(self):
    from repo_workflow.public_cli import handle_public
    pending = StringIO()
    with patch("repo_workflow.public_cli.remote_status",
               return_value=75):
      with patch("repo_workflow.public_cli.configure_ticket_merge_driver") as merge:
        with redirect_stdout(pending):
          self.assertEqual(handle_public(
            self.root, ["remote-status", "--poll", "0"],
            engine_root=self.root,
          ), 75)
        merge.assert_not_called()

  def test_cli_red_submission_validates_selection_before_cmd_transport(self):
    from repo_workflow.public_cli import handle_public
    with patch("repo_workflow.public_cli.read_selection",
               return_value="issue-790-red"):
      with patch("repo_workflow.public_cli.red_declaration",
                 return_value=(object(), "")):
        with patch("repo_workflow.public_cli.submit_remote",
                   return_value=0) as submit:
          self.assertEqual(handle_public(
            self.root, ["test", "RED", "--remote", "--poll", "0.1"],
            engine_root=self.root,
          ), 0)
          self.assertEqual(submit.call_args.args[1],
                           ["test", "RED", "--remote"])
          self.assertEqual(submit.call_args.kwargs["intervals"], (0.1,))

  def test_cli_red_missing_declaration_cannot_publish_cmd(self):
    from repo_workflow.public_cli import handle_public
    with patch("repo_workflow.public_cli.read_selection",
               return_value="issue-790-red"):
      with patch("repo_workflow.public_cli.red_declaration",
                 return_value=(None, "expected-failure-declaration-missing")):
        with patch("repo_workflow.public_cli.submit_remote") as submit:
          with self.assertRaisesRegex(RemoteStatusError, "declaration"):
            handle_public(
              self.root, ["test", "RED", "--remote"],
              engine_root=self.root,
            )
          submit.assert_not_called()

  def test_stale_polled_attempt_is_not_accepted(self):
    pending = CommandStatus(2, "CMD-2-issue-790",
                            "b" * 40, 1, "running", None, 123)
    with patch("repo_workflow.remote_status.command_status",
               return_value=pending):
      with self.assertRaisesRegex(RemoteStatusError, "superseded"):
        remote_status(
          self.root, expected_request="a" * 40, intervals=(0.0,),
          sleep=lambda _: self.fail("must not sleep after stale response"),
        )


if __name__ == "__main__":
  unittest.main()
