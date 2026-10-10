from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


PATH = Path(__file__).resolve().parents[1] / "adapters" / "repo-host-github.py"
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
        self.assertEqual(json.loads(stderr)["error"], "unsupported")

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
        self.assertEqual(json.loads(stderr)["error"], "unsupported")
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

  def test_deterministic_retries_are_read_only(self):
    original = request(request_id="repeat-1")
    self.assertEqual(MODULE.run(original), MODULE.run(original))
    second = json.loads(MODULE.run(request(request_id="repeat-2"))[1])
    self.assertEqual(second["request_id"], "repeat-2")


if __name__ == "__main__":
  unittest.main()
