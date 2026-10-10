from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
import unittest


PATH = Path(__file__).resolve().parents[1] / "adapters" / "repo-host-github.py"
sys.path.insert(0, str(PATH.parent))
SPEC = importlib.util.spec_from_file_location("repo_host_github", PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def request(operation="capabilities", parameters=None, **overrides):
  value = {
    "schema_version": 1,
    "operation": operation,
    "repository": "owner/repo",
    "request_id": "req-1",
    "parameters": {} if parameters is None else parameters,
  }
  value.update(overrides)
  return json.dumps(value)



SHA = "a" * 40
VALID_PARAMS = {
  "issue.update": {"number": 12, "title": "New title"},
  "issue.comment": {"number": 12, "body": "Comment"},
  "pull_request.create": {
    "source_ref": "refs/heads/work",
    "target_ref": "refs/heads/main",
    "expected_source_sha": SHA,
    "title": "Proposal",
    "body": "",
    "draft": True,
  },
  "pull_request.update": {
    "number": 13, "expected_head_sha": SHA, "draft": False,
  },
  "pull_request.merge": {
    "number": 13, "tested_head_sha": SHA,
    "expected_destination_sha": SHA,
    "eligibility_ref": "verified-eligibility",
    "authorization_ref": "verified-authorization",
  },
  "check.publish": {
    "candidate_sha": SHA, "context": "trusted/context",
    "verification_ref": "verified-proof", "conclusion": "failure",
  },
}

class GitHubHostBootstrapTests(unittest.TestCase):

  def test_capabilities_denies_every_mutation(self):
    status, stdout, stderr = MODULE.run(request())
    self.assertEqual(status, 0)
    self.assertEqual(stderr, "")
    response = json.loads(stdout)
    self.assertEqual(set(response), {
      "schema_version", "operation", "repository", "request_id",
      "status", "result",
    })
    self.assertEqual(response["status"], "unchanged")
    self.assertEqual(response["request_id"], "req-1")
    self.assertEqual(
      set(response["result"]["operations"]), set(MODULE.OPERATIONS)
    )
    self.assertFalse(any(response["result"]["operations"].values()))

  def test_every_mutation_fails_closed(self):
    for operation in MODULE.OPERATIONS:
      with self.subTest(operation=operation):
        status, stdout, stderr = MODULE.run(
          request(operation, VALID_PARAMS[operation])
        )
        self.assertNotEqual(status, 0)
        self.assertEqual(stdout, "")
        self.assertIn(
          json.loads(stderr)["error"], {"unauthorized", "unsupported"}
        )

  def test_invalid_envelopes_never_succeed(self):
    bad = [
      "", "{", "[]", "null", "true",
      request(schema_version=True),
      request(schema_version=2),
      request(request_id=""),
      request(request_id="bad id"),
      request(repository="bad"),
      request(repository="a/b/c"),
      request(parameters=[]),
      request(parameters={"extra": 1}),
      request(operation="unknown"),
      request(extra=True),
    ]
    for raw in bad:
      with self.subTest(raw=raw):
        status, stdout, stderr = MODULE.run(raw)
        self.assertNotEqual(status, 0)
        self.assertEqual(stdout, "")
        self.assertEqual(set(json.loads(stderr)), {
          "schema_version", "operation", "repository", "request_id",
          "error", "message",
        })


  def test_exact_mutation_parameter_grammar(self):
    for operation, params in VALID_PARAMS.items():
      with self.subTest(operation=operation):
        status, stdout, stderr = MODULE.run(request(operation, params))
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertIn(
          json.loads(stderr)["error"], {"unauthorized", "unsupported"}
        )
        for mutation in [
          {**params, "unexpected": "x"},
          {key: value for key, value in params.items()
           if key != next(iter(params))},
        ]:
          result = MODULE.run(request(operation, mutation))
          self.assertEqual(result[0], 2)
          self.assertEqual(json.loads(result[2])["error"], "invalid_request")

  def test_untrusted_sha_types_and_values_are_rejected(self):
    for bad in ["A" * 40, "a" * 39, "g" * 40, True, 1, None, []]:
      with self.subTest(bad=bad):
        params = {**VALID_PARAMS["pull_request.merge"],
                  "tested_head_sha": bad}
        status, stdout, stderr = MODULE.run(
          request("pull_request.merge", params)
        )
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error"], "invalid_request")


  def test_duplicate_json_keys_fail_including_nested_parameters(self):
    raw = request().replace('"request_id": "req-1"', (
      '"request_id": "req-1", "request_id": "shadow"'
    ))
    for bad in [raw, request().replace('"parameters": {}', (
      '"parameters": {"number": 1, "number": 2}'
    ))]:
      with self.subTest(bad=bad):
        status, stdout, stderr = MODULE.run(bad)
        self.assertNotEqual(status, 0)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error"], "invalid_request")

  def test_issue_close_is_valid_but_pr_close_is_refused(self):
    issue = MODULE.run(request(
      "issue.update", {"number": 7, "state": "closed"}
    ))
    self.assertEqual(json.loads(issue[2])["error"], "unauthorized")
    pr = MODULE.run(request(
      "pull_request.update",
      {"number": 7, "expected_head_sha": SHA, "state": "closed"}
    ))
    self.assertEqual(json.loads(pr[2])["error"], "invalid_request")

  def test_zero_boolean_and_string_numbers_are_rejected(self):
    for number in [0, -1, True, False, "1", None, [], 1.5]:
      with self.subTest(number=number):
        params = {"number": number, "body": "test"}
        result = MODULE.run(request("issue.comment", params))
        self.assertEqual(json.loads(result[2])["error"], "invalid_request")


  def test_rejects_relative_and_ambiguous_git_refs(self):
    good = VALID_PARAMS["pull_request.create"]
    for bad in [
      "main", "refs/tags/v1", "refs/heads/../main",
      "refs/heads/a//b", "refs/heads/", "refs/heads/a.lock",
      "refs/heads/-bad;rm", 23, None,
    ]:
      with self.subTest(ref=bad):
        params = {**good, "source_ref": bad}
        status, stdout, stderr = MODULE.run(
          request("pull_request.create", params)
        )
        self.assertNotEqual(status, 0)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error"], "invalid_request")

  def test_cli_stdin_stdout_stderr_and_exit_codes(self):
    valid = subprocess.run(
      [sys.executable, str(PATH)], input=request(),
      capture_output=True, text=True, check=False,
    )
    self.assertEqual(valid.returncode, 0)
    self.assertEqual(valid.stderr, "")
    self.assertEqual(json.loads(valid.stdout)["status"], "unchanged")
    denied = subprocess.run(
      [sys.executable, str(PATH)],
      input=request("issue.comment", VALID_PARAMS["issue.comment"]),
      capture_output=True, text=True, check=False,
    )
    self.assertNotEqual(denied.returncode, 0)
    self.assertEqual(denied.stdout, "")
    self.assertEqual(json.loads(denied.stderr)["error"], "unauthorized")


  def test_error_retains_parseable_request_identity(self):
    raw = request("issue.comment", {"number": 0, "body": "bad"})
    status, stdout, stderr = MODULE.run(raw)
    self.assertNotEqual(status, 0)
    self.assertEqual(stdout, "")
    value = json.loads(stderr)
    self.assertEqual(value["operation"], "issue.comment")
    self.assertEqual(value["repository"], "owner/repo")
    self.assertEqual(value["request_id"], "req-1")

  def test_concatenated_requests_are_invalid_not_partially_executed(self):
    status, stdout, stderr = MODULE.run(request() + request())
    self.assertNotEqual(status, 0)
    self.assertEqual(stdout, "")
    self.assertEqual(json.loads(stderr)["error"], "invalid_request")


  def test_deep_or_oversized_request_returns_structured_error(self):
    for bad in [
      "[" * 2000 + "0" + "]" * 2000,
      " " * (MODULE.MAX_REQUEST_CHARS + 1),
    ]:
      with self.subTest(length=len(bad)):
        status, stdout, stderr = MODULE.run(bad)
        self.assertNotEqual(status, 0)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error"], "invalid_request")


  def test_live_probe_parses_without_provider_side_effects(self):
    probe = PATH.parents[1] / "scripts" / "probe-repo-host-github.py"
    help_result = subprocess.run(
      [sys.executable, str(probe), "--help"],
      capture_output=True, text=True, check=False,
    )
    self.assertEqual(help_result.returncode, 0)
    invalid = subprocess.run(
      [sys.executable, str(probe), "--repository", "owner/repo",
       "--sandbox-issue", "0", "--source-ref", "refs/heads/work",
       "--target-ref", "refs/heads/main", "--run-id", "local-test"],
      capture_output=True, text=True, check=False,
    )
    self.assertNotEqual(invalid.returncode, 0)
    self.assertIn("positive", invalid.stderr)

  def test_deterministic_retries_are_read_only(self):
    original = request(request_id="repeat-1")
    self.assertEqual(MODULE.run(original), MODULE.run(original))
    second = json.loads(MODULE.run(request(request_id="repeat-2"))[1])
    self.assertEqual(second["request_id"], "repeat-2")


if __name__ == "__main__":
  unittest.main()
