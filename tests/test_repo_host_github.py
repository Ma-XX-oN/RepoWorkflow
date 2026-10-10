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
        status, stdout, stderr = MODULE.run(request(operation))
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

  def test_deterministic_retries_are_read_only(self):
    original = request(request_id="repeat-1")
    self.assertEqual(MODULE.run(original), MODULE.run(original))
    second = json.loads(MODULE.run(request(request_id="repeat-2"))[1])
    self.assertEqual(second["request_id"], "repeat-2")


if __name__ == "__main__":
  unittest.main()
