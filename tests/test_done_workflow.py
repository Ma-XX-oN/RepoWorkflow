"""Real local Git and executable catalogue checks for functional completion."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from repo_workflow.done_results import platform_name
from repo_workflow.done_workflow import accept_done, completed_submission, prepare_done, run_done_tests
from repo_workflow.git import git
from repo_workflow.test_results_reader import TestCommandError
from tests import test_done_submission as _submission


class DoneWorkflowTests(unittest.TestCase):
  """Exercise actual tests and Git writes without external verifier programs."""

  setUp = _submission.DoneSubmissionTests.setUp
  commit = _submission.DoneSubmissionTests.commit
  refs = _submission.DoneSubmissionTests.refs
  invoke = _submission.DoneSubmissionTests.invoke
  advance_parent = _submission.DoneSubmissionTests.advance_parent

  def prepared(self, *, fail=False, manual=False):
    """Commit two executable checks and prepare their genuine submission."""
    (self.root / ".repoworkflow").mkdir(exist_ok=True)
    (self.root / ".repoworkflow/tickets.csv").write_text(
      "issue,title,dependencies,state\n51,Issue 51,,active\n", encoding="utf-8")
    for stage in ("regression", "integration"):
      (self.root / (stage + ".py")).write_text(
        "from pathlib import Path\nassert Path('feature').read_text() == 'issue work\\n'\n"
        + ("raise SystemExit(1)\n" if fail and stage == "integration" else ""),
        encoding="utf-8", newline="\n")
    catalogue = {"test-harnesses": {"script": {"command": "python", "layout": ["$test"]}},
      "tests": [{"test-harness": "script",
        "check-regression": {"type": "regression", "name": "regression.py"},
        "check-integration": {"type": "integration", "name": "integration.py"}}]}
    if manual:
      catalogue["tests"].append({"test-harness": "script", "issue-51-manual--CHECK": {
        "type": "manual", "instructions": "Inspect the feature with an external tester.",
        "expected_result": "The feature matches the request."}})
    (self.root / ".ci").mkdir(exist_ok=True)
    (self.root / ".ci/tests.json").write_text(json.dumps(catalogue), encoding="utf-8", newline="\n")
    self.commit("test: add executable checks")
    submission = self.invoke()
    plan = prepare_done(self.root, submission["prelim_ref"], engine_root=self.root)
    self.assertEqual(set(plan["platforms"]), {"linux", "windows", "macos"})
    return plan

  def single_platform(self):
    """Select a single-platform policy fixture without fabricating test results."""
    return {**self.prepared(), "platforms": [platform_name()]}

  def test_actual_tests_merge_reports_complete_lifecycle_and_retire_one_prelim(self):
    """The functional path runs real scripts and atomically updates a bare Git parent."""
    plan = self.single_platform()
    original = git(self.root, "rev-parse", "HEAD").stdout.strip()
    with patch.dict("os.environ", {"RWF_REPO_HOST_AUTH_COMMAND": "", "RWF_REPO_HOST_INTEGRATION_EVIDENCE_COMMAND": ""}), \
        patch("repo_workflow.test_cli.reusable_local_group_passes",
          side_effect=AssertionError("worker must use its platform-aware selection")):
      self.assertEqual(run_done_tests(self.root, plan)["status"], "tested")
      result = accept_done(self.root, plan)
    self.assertEqual(result["status"], "done")
    self.assertEqual(self.refs()["refs/heads/main"], result["landed_sha"])
    self.assertNotIn(plan["prelim_ref"], self.refs())
    self.assertEqual(result["tested_source_sha"], plan["candidate_sha"])
    self.assertNotEqual(original, result["landed_sha"])
    tickets = git(self.root, "show", result["landed_sha"] + ":.repoworkflow/tickets.csv").stdout
    self.assertIn("51,Issue 51,,completed", tickets)
    self.assertNotIn("lifecycle.json", git(self.root, "ls-tree", "-r", "--name-only", result["landed_sha"]).stdout)
    self.assertEqual(accept_done(self.root, plan), result)
    self.assertEqual(completed_submission(self.root, 51), result)

  def test_unchanged_resume_does_not_execute_passing_groups_again(self):
    """Only missing registered groups execute; integration reuses regression checks."""
    plan = self.single_platform()
    with contextlib.redirect_stdout(io.StringIO()):
      self.assertEqual(run_done_tests(self.root, plan)["status"], "tested")
    with patch("repo_workflow.test_cli._run_group_set", side_effect=AssertionError("must reuse actual PASS")):
      self.assertEqual(run_done_tests(self.root, plan)["status"], "tested")

  def test_missing_other_platforms_never_merges(self):
    """A real current-platform PASS is insufficient for a three-platform plan."""
    plan = self.prepared()
    run_done_tests(self.root, plan)
    self.assertEqual(accept_done(self.root, plan)["status"], "waiting")
    self.assertEqual(self.refs()["refs/heads/main"], plan["parent_sha"])

  def test_parent_advancing_after_tests_requires_reconstruction(self):
    """The stale result never writes or rolls back the destination."""
    plan = self.single_platform()
    run_done_tests(self.root, plan)
    parent = self.advance_parent()
    self.assertEqual(accept_done(self.root, plan)["status"], "stale")
    refreshed = prepare_done(self.root, plan["prelim_ref"], engine_root=self.root)
    self.assertEqual(refreshed["parent_sha"], parent)
    self.assertNotEqual(refreshed["candidate_sha"], plan["candidate_sha"])
    self.assertEqual(self.refs()["refs/heads/main"], parent)

  def test_latest_numeric_version_supersedes_an_older_requested_ref(self):
    """An earlier submission is ignored even when it has actual passing results."""
    plan = self.single_platform()
    run_done_tests(self.root, plan)
    (self.root / "new-source").write_text("correction\n", encoding="utf-8")
    self.commit("fix: new source")
    self.invoke()
    self.assertEqual(prepare_done(self.root, plan["prelim_ref"], engine_root=self.root)["status"], "ignored")
    self.assertEqual(accept_done(self.root, plan)["status"], "ignored")

  def test_retiring_latest_does_not_reactivate_an_old_pending_prelim(self):
    """Completion history keeps the last version authoritative after ref cleanup."""
    old = self.prepared()
    (self.root / "new-source").write_text("new work\n", encoding="utf-8")
    self.commit("fix: new candidate")
    submission = self.invoke()
    plan = prepare_done(self.root, submission["prelim_ref"], engine_root=self.root)
    plan["platforms"] = [platform_name()]
    run_done_tests(self.root, plan)
    accept_done(self.root, plan)
    self.assertIn(old["prelim_ref"], self.refs())
    result = prepare_done(self.root, old["prelim_ref"], engine_root=self.root)
    self.assertEqual(result["status"], "done")
    self.assertEqual(result["version"], plan["version"])

  def test_actual_failed_test_preserves_parent_and_publishes_fail_tag(self):
    """A genuine executable failure is durable and prevents acceptance."""
    plan = {**self.prepared(fail=True), "platforms": [platform_name()]}
    self.assertEqual(run_done_tests(self.root, plan)["status"], "failed")
    self.assertEqual(self.refs()["refs/heads/main"], plan["parent_sha"])
    self.assertTrue(any("CI-FAIL" in ref for ref in self.refs()))
    with self.assertRaises(TestCommandError):
      accept_done(self.root, plan)

  def test_internal_cli_prepares_the_actual_submission(self):
    """The workflow entry point reads the genuine Git submission and writes its plan."""
    plan = self.prepared()
    engine = Path(__file__).resolve().parents[1]
    output = self.root.parent / "worker-plan.json"
    completed = subprocess.run([sys.executable, str(engine / "repo_workflow.py"),
      "--root", str(self.root), "done-worker", "prepare", "--prelim-ref", plan["prelim_ref"],
      "--output", str(output)], capture_output=True, text=True)
    self.assertEqual(completed.returncode, 0, completed.stderr)
    self.assertEqual(json.loads(output.read_text())["candidate_sha"], plan["candidate_sha"])

  def test_configured_environment_is_executed_and_reused(self):
    """Consumer validation commands contribute actual reusable results."""
    from repo_workflow.done_environments import pending_environments
    plan = {**self.single_platform(), "engine": False}
    config = {"environments": [{"id": "native", "platform": platform_name(),
      "required": True, "validationCommand": [sys.executable, "-c",
        "from pathlib import Path; assert Path('feature').read_text() == 'issue work\\n'"]}]}
    with patch("repo_workflow.done_environments.load_config", return_value=config):
      self.assertEqual(len(pending_environments(self.root, plan)), 1)
      self.assertEqual(run_done_tests(self.root, plan)["status"], "tested")
      self.assertEqual(pending_environments(self.root, plan), [])
      with patch("repo_workflow.done_environments._run_environment_for_candidate",
          side_effect=AssertionError("must reuse actual environment PASS")):
        self.assertEqual(run_done_tests(self.root, plan)["status"], "tested")

  def test_external_manual_result_is_required_and_survives_report_exchange(self):
    """Missing manual work waits; a real recorded external verdict permits merge."""
    from repo_workflow.done_manual_resume import resume_manual_done
    from repo_workflow.manual_test_catalogue import read_manual_cases
    from repo_workflow.manual_test_state import select_manual_case
    from repo_workflow.manual_test_result import record_manual_result
    plan = {**self.prepared(manual=True), "platforms": [platform_name()]}
    run_done_tests(self.root, plan)
    self.assertEqual(accept_done(self.root, plan)["manual"], ["issue-51-manual--CHECK"])
    git(self.root, "checkout", "-b", "external-tester")
    cases = read_manual_cases(self.root, 51)
    select_manual_case(self.root, 51, plan["candidate_sha"], cases[0], cases=cases)
    record_manual_result(self.root, 51, plan["candidate_sha"], "succeeded",
      operator="external-fixture-tester", cases=cases)
    with patch("repo_workflow.done_workflow.dispatch_done", return_value={"status": "submitted"}) as dispatch:
      self.assertEqual(resume_manual_done(self.root, 51, plan["candidate_sha"], complete=True)["status"], "submitted")
      dispatch.assert_called_once()
    self.assertEqual(accept_done(self.root, plan)["status"], "done")

  def test_parent_race_at_push_cannot_merge_or_roll_back(self):
    """The expected-old lease rejects a parent change after the last read."""
    plan = self.single_platform()
    run_done_tests(self.root, plan)
    advanced = []

    def racing_git(root, *args, **kwargs):
      """Advance the genuine bare-Git parent immediately before publication."""
      if args[:2] == ("push", "--atomic") and not advanced:
        advanced.append(self.advance_parent())
      return git(root, *args, **kwargs)

    with patch("repo_workflow.done_workflow.git", side_effect=racing_git):
      self.assertEqual(accept_done(self.root, plan)["status"], "stale")
    self.assertEqual(self.refs()["refs/heads/main"], advanced[0])
    self.assertIn(plan["prelim_ref"], self.refs())

  def test_lost_push_acknowledgement_reconciles_actual_completion(self):
    """A transport error after a successful atomic write is reconciled by readback."""
    plan = self.single_platform()
    run_done_tests(self.root, plan)

    def lost_ack_git(root, *args, **kwargs):
      """Perform the real publication, then simulate loss of its acknowledgement."""
      result = git(root, *args, **kwargs)
      return subprocess.CompletedProcess(result.args, 1, result.stdout, result.stderr) if args[:2] == ("push", "--atomic") else result

    with patch("repo_workflow.done_workflow.git", side_effect=lost_ack_git):
      result = accept_done(self.root, plan)
    self.assertEqual(result["status"], "done")
    self.assertEqual(self.refs()["refs/heads/main"], result["landed_sha"])

  def test_conflict_retains_notification_outcome_and_does_not_resend(self):
    """A real merge conflict retains its handoff and one outgoing delivery result."""
    (self.root / "file").write_text("issue change\n", encoding="utf-8")
    self.commit("fix: conflicting source")
    plan = self.prepared()
    parent = self.advance_parent(conflict=True)
    with patch("repo_workflow.done_email.send_conflict_email",
        side_effect=lambda root, payload: {**payload, "status": "failed", "error": "fixture unavailable"}) as sender:
      result = prepare_done(self.root, plan["prelim_ref"], engine_root=self.root)
      resumed = prepare_done(self.root, plan["prelim_ref"], engine_root=self.root)
      sender.assert_called_once()
    self.assertEqual(result["status"], "conflict")
    self.assertEqual(resumed, result)
    self.assertEqual(result["notification"]["status"], "failed")
    self.assertIn("file", result["notification"]["body"])
    self.assertEqual(self.refs()["refs/heads/main"], parent)


class ConflictEmailTests(unittest.TestCase):
  """Verify outgoing mail formatting and failure reporting without sending mail."""

  def test_configured_smtp_sends_the_conflict_to_the_configured_user(self):
    """The outgoing client sends the supplied subject/body and records delivery."""
    from repo_workflow.done_email import send_conflict_email
    payload = {"to": "author@example.com", "subject": "RWF issue 51: integration conflict", "body": "Source: abc\nParent: def\nconflicting feature"}
    with patch.dict("os.environ", {"SMTP_HOST": "smtp.example.com", "SMTP_FROM": "rwf@example.com",
        "SMTP_USERNAME": "rwf", "SMTP_PASSWORD": "fixture", "RWF_NOTIFICATION_EMAIL": "user@example.com"}, clear=True), \
        patch("repo_workflow.done_email.git") as configured, \
        patch("repo_workflow.done_email.ssl.create_default_context"), \
        patch("repo_workflow.done_email.smtplib.SMTP") as smtp:
      configured.return_value.stdout = ""
      client = smtp.return_value
      client.send_message.return_value = {}
      result = send_conflict_email(Path.cwd(), payload)
      self.assertEqual(result["status"], "sent")
      message = client.send_message.call_args.args[0]
      self.assertEqual(message["To"], "user@example.com")
      self.assertEqual(message.get_content().strip(), payload["body"])
      client.starttls.assert_called_once()
      client.login.assert_called_once_with("rwf", "fixture")

  def test_unavailable_smtp_retains_a_failed_delivery(self):
    """An outgoing transport failure remains explicit without leaking credentials."""
    from repo_workflow.done_email import send_conflict_email
    with patch.dict("os.environ", {"SMTP_HOST": "smtp.example.com", "SMTP_FROM": "rwf@example.com"}, clear=True), \
        patch("repo_workflow.done_email.git") as configured, \
        patch("repo_workflow.done_email.ssl.create_default_context"), \
        patch("repo_workflow.done_email.smtplib.SMTP", side_effect=OSError("private detail")):
      configured.return_value.stdout = ""
      result = send_conflict_email(Path.cwd(), {"to": "user@example.com", "subject": "Conflict", "body": "actual conflict"})
      self.assertEqual(result["status"], "failed")
      self.assertEqual(result["error"], "OSError")

  def test_workflow_runs_each_platform_and_accepts_only_after_tests(self):
    """The hosted adapter uses the shared worker and checks its native matrix."""
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/prelim-done.yml").read_text()
    self.assertIn("os: [ubuntu-latest, windows-latest, macos-latest]", workflow)
    self.assertIn("needs.test.result == 'success'", workflow)
    for phase in ("prepare", "test", "accept", "dispatch"):
      self.assertIn("done-worker " + phase, workflow)
    self.assertIn("needs.prepare.outputs.candidate", workflow)
    forwarding = (root / ".github/workflows/remote-rwf.yml").read_text()
    self.assertIn('engine_sha="$GITHUB_SHA"', forwarding)
    self.assertIn("actions: write", forwarding)
