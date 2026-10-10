"""Black-box contract tests for the portable host mutation boundary."""
import json
import subprocess
import sys
import unittest
import tempfile
from pathlib import Path
from repo_workflow.config import ConfigError, load_config
from repo_workflow.host_mutation_dispatch import dispatch_configured
from unittest.mock import patch

from repo_workflow.host_mutation_dispatch import HostMutationError, dispatch


SHA = "a" * 40
BASE = {
  "schema_version": 1, "operation": "issue.comment",
  "repository": "owner/project", "request_id": "once-1",
  "parameters": {"number": 11, "body": "test"},
}
OPS = (
  "issue.update", "issue.comment", "pull_request.create",
  "pull_request.update", "pull_request.merge", "check.publish",
)
PARAMS = {
  "issue.update": {"number": 11, "title": "updated"},
  "issue.comment": {"number": 11, "body": "test"},
  "pull_request.create": {
    "source_ref": "refs/heads/source", "target_ref": "refs/heads/main",
    "expected_source_sha": SHA, "title": "PR", "body": "",
    "draft": True,
  },
  "pull_request.update": {
    "number": 11, "expected_head_sha": SHA, "title": "new",
  },
  "pull_request.merge": {
    "number": 11, "tested_head_sha": SHA,
    "expected_destination_sha": SHA, "eligibility_ref": "proof",
    "authorization_ref": "authority",
  },
  "check.publish": {
    "candidate_sha": SHA, "context": "required",
    "verification_ref": "evidence", "conclusion": "success",
  },
}
RESULTS = {
  "issue.update": {"number": 11, "title": "updated", "state": "open"},
  "issue.comment": {"number": 11, "comment_id": "provider-42"},
  "pull_request.create": {
    "number": 11, "source_ref": "refs/heads/source",
    "target_ref": "refs/heads/main", "head_sha": SHA, "draft": True,
  },
  "pull_request.update": {
    "number": 11, "head_sha": SHA, "target_ref": "refs/heads/main",
    "draft": False, "state": "open",
  },
  "pull_request.merge": {
    "number": 11, "merged_head_sha": SHA, "destination_sha": "b" * 40,
  },
  "check.publish": {
    "candidate_sha": SHA, "context": "required",
    "check_id": "check-42", "conclusion": "success",
  },
}


def request(operation="issue.comment"):
  return dict(BASE, operation=operation, parameters=PARAMS[operation].copy())


def response(req, *, result=None, **changes):
  operation = req["operation"]
  value = {
    "schema_version": 1, "operation": operation,
    "repository": req["repository"], "request_id": req["request_id"],
    "status": "unchanged" if operation == "capabilities" else "applied",
    "result": (
      {"operations": {name: True for name in OPS}}
      if operation == "capabilities" else RESULTS[operation]
    ) if result is None else result,
  }
  return json.dumps(dict(value, **changes))


class Completed:
  def __init__(self, out="", status=0, err=""):
    self.stdout, self.returncode, self.stderr = out, status, err


def provider_success(req, **changes):
  return Completed(response(req, **changes))


class DispatcherContractTests(unittest.TestCase):
  def run_provider(self, req, run=None):
    calls = []
    def execute(argv, **kwargs):
      received = json.loads(kwargs["input"])
      calls.append(received)
      return run(received) if run else provider_success(received)
    with patch(
      "repo_workflow.host_mutation_dispatch.subprocess.run",
      side_effect=execute,
    ):
      answer = dispatch(["provider"], req)
    return answer, calls

  def test_all_operations_inquire_before_mutation(self):
    for operation in OPS:
      with self.subTest(operation=operation):
        req = request(operation)
        answer, calls = self.run_provider(req)
        self.assertEqual(answer["result"], RESULTS[operation])
        self.assertEqual([x["operation"] for x in calls], [
          "capabilities", operation,
        ])
        self.assertEqual(calls[1], req)
        self.assertEqual(calls[0]["parameters"], {})

  def test_unsupported_capability_never_mutates(self):
    req = request()
    calls = []
    def runner(received):
      calls.append(received["operation"])
      return provider_success(
        received, result={"operations": {
          name: name != "issue.comment" for name in OPS
        }},
      )
    with self.assertRaises(HostMutationError) as caught:
      self.run_provider(req, runner)
    self.assertEqual(caught.exception.code, "unsupported")
    self.assertEqual(calls, ["capabilities"])

  def test_invalid_parameters_never_call_provider(self):
    for operation in OPS:
      req = request(operation)
      changes = (
        {"number": True}, {"number": "11"}, {"unexpected": True},
      )
      for patch_values in changes:
        altered = dict(req, parameters=dict(req["parameters"], **patch_values))
        with self.subTest(operation=operation, patch=patch_values):
          with patch(
            "repo_workflow.host_mutation_dispatch.subprocess.run",
          ) as run:
            with self.assertRaises(HostMutationError):
              dispatch(["provider"], altered)
            run.assert_not_called()

  def test_response_schema_rejects_missing_or_wrong_fields(self):
    req = request()
    wrong_results = (
      {"comment_id": "provider-42"},
      {"number": True, "comment_id": "provider-42"},
      {"number": 12, "comment_id": "provider-42"},
      {"number": 11, "comment_id": ""},
      {"number": 11, "comment_id": "ok", "extra": 1},
    )
    for value in wrong_results:
      with self.subTest(value=value):
        def runner(received):
          return provider_success(
            received,
            result=value if received["operation"] != "capabilities" else None,
          )
        with self.assertRaises(HostMutationError):
          self.run_provider(req, runner)

  def test_capability_response_requires_exact_boolean_map(self):
    req = request()
    invalid = (
      {}, {"issue.comment": True},
      {name: 1 for name in OPS},
      {**{name: True for name in OPS}, "unknown": True},
    )
    for operations in invalid:
      with self.subTest(operations=operations):
        with self.assertRaises(HostMutationError):
          self.run_provider(req, lambda received: provider_success(
            received, result={"operations": operations},
          ))

  def test_typed_nonzero_error_propagates_without_retry(self):
    req = request()
    calls = []
    def runner(received):
      calls.append(received["operation"])
      if received["operation"] == "capabilities":
        return provider_success(received)
      error = dict(
        schema_version=1, operation=received["operation"],
        repository=received["repository"], request_id=received["request_id"],
        error="unauthorized", message="permission denied",
      )
      return Completed("", 1, json.dumps(error))
    with self.assertRaises(HostMutationError) as caught:
      self.run_provider(req, runner)
    self.assertEqual(caught.exception.code, "unauthorized")
    self.assertEqual(calls, ["capabilities", "issue.comment"])

  def test_failure_stdout_and_bad_error_fail_closed(self):
    req = request()
    for failed in (
      Completed("{}", 1, ""),
      Completed("", 1, "not-json"),
      Completed("", 1, '{"error":"conflict"}'),
    ):
      def runner(received):
        if received["operation"] == "capabilities":
          return provider_success(received)
        return failed
      with self.assertRaises(HostMutationError):
        self.run_provider(req, runner)

  def test_request_identity_failures_have_no_side_effects(self):
    for changed in (
      {"schema_version": True}, {"schema_version": 2},
      {"operation": "unknown"}, {"repository": "invalid"},
      {"request_id": ""}, {"request_id": "has whitespace"},
      {"request_id": "x" * 129}, {"parameters": []},
      {"extra": 1},
    ):
      with self.subTest(changed=changed):
        with patch(
          "repo_workflow.host_mutation_dispatch.subprocess.run",
        ) as run:
          with self.assertRaises(HostMutationError):
            dispatch(["provider"], dict(BASE, **changed))
          run.assert_not_called()

  def test_repeated_request_preserves_id_and_no_hidden_retry(self):
    req = request()
    _, first = self.run_provider(req)
    _, second = self.run_provider(req)
    self.assertEqual(first, second)
    self.assertEqual(first[-1]["request_id"], "once-1")

  def test_timeout_is_unknown_not_success(self):
    with patch(
      "repo_workflow.host_mutation_dispatch.subprocess.run",
      side_effect=subprocess.TimeoutExpired(["provider"], 1),
    ):
      with self.assertRaises(HostMutationError) as caught:
        dispatch(["provider"], request())
    self.assertEqual(caught.exception.code, "unknown_outcome")

  def test_real_subprocess_round_trip_with_capability(self):
    script = (
      "import json,sys;"
      "x=json.load(sys.stdin);"
      "o=x['operation'];"
      "r=({'operations':{k:True for k in "
      "('issue.update','issue.comment','pull_request.create',"
      "'pull_request.update','pull_request.merge','check.publish')}} "
      "if o=='capabilities' else {'number':11,'comment_id':'real'});"
      "print(json.dumps(dict(schema_version=1,operation=o,"
      "repository=x['repository'],request_id=x['request_id'],"
      "status='unchanged' if o=='capabilities' else 'applied',result=r)))"
    )
    actual = dispatch([sys.executable, "-c", script], request())
    self.assertEqual(actual["result"]["comment_id"], "real")


  def test_configured_command_is_resolved_without_invented_default(self):
    req = request()
    with tempfile.TemporaryDirectory() as folder:
      root = Path(folder)
      ci = root / ".ci"
      ci.mkdir()
      conf = {
        "schema": 1, "versionCommand": ["python", "version.py"],
        "repository": {
          "integrationBranch": "main", "authoritativeRemote": "origin",
        },
        "environments": [{
          "id": "linux", "validationCommand": ["python", "validate.py"],
        }],
        "hostCommand": ["configured-provider", "host"],
      }
      path = ci / "repoworkflow.json"
      path.write_text(json.dumps(conf), encoding="utf-8")
      self.assertEqual(load_config(root)["hostCommand"], conf["hostCommand"])
      for args in (
        ("init", "-q"), ("config", "user.email", "test@example.invalid"),
        ("config", "user.name", "Test"), ("add", "."),
        ("commit", "-qm", "fixture"),
      ):
        subprocess.run(["git", *args], cwd=root, check=True)
      with patch(
        "repo_workflow.host_mutation_dispatch.dispatch",
        return_value={"result": RESULTS["issue.comment"]},
      ) as invoked:
        reply = dispatch_configured(root, req)
      self.assertEqual(reply["result"]["number"], 11)
      invoked.assert_called_once_with(
        conf["hostCommand"], req, timeout=30,
      )

      def mutate(*_args, **_kwargs):
        (root / "mutated-by-adapter").write_text("unexpected")
        return {"result": RESULTS["issue.comment"]}
      with patch(
        "repo_workflow.host_mutation_dispatch.dispatch",
        side_effect=mutate,
      ):
        with self.assertRaisesRegex(
          HostMutationError, "changed local repository state",
        ):
          dispatch_configured(root, req)
      (root / "mutated-by-adapter").unlink()

      del conf["hostCommand"]
      path.write_text(json.dumps(conf), encoding="utf-8")
      with patch(
        "repo_workflow.host_mutation_dispatch.dispatch",
      ) as run:
        with self.assertRaises(HostMutationError):
          dispatch_configured(root, req)
        run.assert_not_called()

      conf["hostCommand"] = "shell string"
      path.write_text(json.dumps(conf), encoding="utf-8")
      with self.assertRaises(ConfigError):
        load_config(root)
      with patch(
        "repo_workflow.host_mutation_dispatch.dispatch",
      ) as run:
        with self.assertRaises(HostMutationError):
          dispatch_configured(root, req)
        run.assert_not_called()

  def test_response_identity_contradictions_fail_closed(self):
    for operation, change in (
      ("issue.comment", {"number": 12, "comment_id": "other"}),
      ("pull_request.create", {
        "number": 11, "source_ref": "refs/heads/other",
        "target_ref": "refs/heads/main", "head_sha": SHA, "draft": True,
      }),
      ("check.publish", {
        "candidate_sha": "b" * 40, "context": "required",
        "check_id": "ok", "conclusion": "success",
      }),
    ):
      req = request(operation)
      def runner(received):
        if received["operation"] == "capabilities":
          return provider_success(received)
        return provider_success(received, result=change)
      with self.subTest(operation=operation):
        with self.assertRaises(HostMutationError):
          self.run_provider(req, runner)


  def test_requested_mutation_fields_must_match_observed_result(self):
    for operation, field, bad in (
      ("issue.update", "title", "wrong"),
      ("pull_request.create", "draft", False),
      ("pull_request.update", "head_sha", "b" * 40),
    ):
      req = request(operation)
      wrong = dict(RESULTS[operation], **{field: bad})
      def runner(received):
        if received["operation"] == "capabilities":
          return provider_success(received)
        return provider_success(received, result=wrong)
      with self.subTest(operation=operation, field=field):
        with self.assertRaises(HostMutationError):
          self.run_provider(req, runner)


if __name__ == "__main__":
  unittest.main()
