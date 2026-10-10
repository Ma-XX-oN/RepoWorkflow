"""Black-box repository-host mutation boundary contract tests."""
import json
from unittest.mock import patch
import subprocess
import unittest

from repo_workflow.host_mutation_dispatch import HostMutationError, dispatch


BASE = {
  "schema_version": 1, "operation": "issue.comment",
  "repository": "owner/project", "request_id": "once-1",
  "parameters": {"number": 11, "body": "test"},
}


class FakeCompleted:
  def __init__(self, stdout="", returncode=0):
    self.stdout = stdout
    self.stderr = ""
    self.returncode = returncode


class HostMutationDispatcherTests(unittest.TestCase):
  def reply(self, request=BASE, **overrides):
    value = {
      "schema_version": 1, "operation": request["operation"],
      "repository": request["repository"],
      "request_id": request["request_id"],
      "status": "applied", "result": {"comment_id": "provider-42"},
    }
    return json.dumps({**value, **overrides})

  def test_semantic_request_forwarded_without_shell_or_reinterpretation(self):
    sent = []
    def fake_run(argv, **kwargs):
      sent.append((argv, kwargs))
      return FakeCompleted(self.reply())
    with patch("repo_workflow.host_mutation_dispatch.subprocess.run",
               side_effect=fake_run):
      self.assertEqual(
        dispatch(["provider", "mutate"], BASE)["result"]["comment_id"],
        "provider-42",
      )
    self.assertEqual(sent[0][0], ["provider", "mutate"])
    self.assertEqual(json.loads(sent[0][1]["input"]), BASE)
    self.assertFalse(sent[0][1].get("shell", False))

  def test_invalid_request_never_executes_adapter(self):
    changes = (
      {"schema_version": True}, {"schema_version": 2},
      {"operation": "github.raw"}, {"operation": []},
      {"repository": "invalid"},
      {"request_id": ""}, {"request_id": "bad whitespace"},
      {"request_id": "x" * 129}, {"parameters": None},
      {"extra": True},
    )
    with patch("repo_workflow.host_mutation_dispatch.subprocess.run") as run:
      for change in changes:
        with self.subTest(change=change):
          with self.assertRaises(HostMutationError):
            dispatch(["provider"], {**BASE, **change})
      run.assert_not_called()

  def test_all_semantic_operations_preserve_identity(self):
    for operation in (
      "capabilities", "issue.update", "issue.comment",
      "pull_request.create", "pull_request.update",
      "pull_request.merge", "check.publish",
    ):
      request = {**BASE, "operation": operation}
      with self.subTest(operation=operation):
        with patch("repo_workflow.host_mutation_dispatch.subprocess.run",
                   return_value=FakeCompleted(self.reply(request))):
          self.assertEqual(
            dispatch(["provider"], request)["operation"], operation,
          )

  def test_malformed_successful_envelopes_fail_closed(self):
    cases = (
      {"schema_version": 2}, {"repository": "other/repo"},
      {"operation": "issue.update"}, {"request_id": "other"},
      {"result": []}, {"status": "pending"}, {"extra": 1},
    )
    for changed in cases:
      with self.subTest(changed=changed):
        with patch("repo_workflow.host_mutation_dispatch.subprocess.run",
                   return_value=FakeCompleted(self.reply(**changed))):
          with self.assertRaises(HostMutationError):
            dispatch(["provider"], BASE)

  def test_missing_adapter_and_provider_failures_are_never_success(self):
    with self.assertRaises(HostMutationError):
      dispatch([], BASE)
    for response in (
      FakeCompleted("", 1), FakeCompleted(""), FakeCompleted("{}"),
      FakeCompleted(self.reply(request_id="wrong")),
      FakeCompleted(self.reply(status="pending")),
      FakeCompleted(self.reply(status=[])),
      FakeCompleted(self.reply(result=[])),
    ):
      with self.subTest(response=response.stdout):
        with patch("repo_workflow.host_mutation_dispatch.subprocess.run",
                   return_value=response):
          with self.assertRaises(HostMutationError):
            dispatch(["provider"], BASE)

  def test_retry_identity_is_unchanged_and_dispatcher_does_not_invent_ids(self):
    seen = []
    def fake_run(argv, **kwargs):
      seen.append(json.loads(kwargs["input"]))
      return FakeCompleted(self.reply(status="unchanged"))
    with patch("repo_workflow.host_mutation_dispatch.subprocess.run",
               side_effect=fake_run):
      for _ in range(2):
        self.assertEqual(dispatch(["provider"], BASE)["status"], "unchanged")
    self.assertEqual(seen, [BASE, BASE])

  def test_failed_provider_is_not_retried_automatically(self):
    with patch("repo_workflow.host_mutation_dispatch.subprocess.run",
               return_value=FakeCompleted(self.reply(), 1)) as run:
      with self.assertRaises(HostMutationError):
        dispatch(["provider"], BASE)
      self.assertEqual(run.call_count, 1)

  def test_timeout_is_unknown_not_idempotent_success(self):
    with patch("repo_workflow.host_mutation_dispatch.subprocess.run",
               side_effect=subprocess.TimeoutExpired(["provider"], 1)):
      with self.assertRaisesRegex(HostMutationError, "outcome unavailable"):
        dispatch(["provider"], BASE)


if __name__ == "__main__":
  unittest.main()
