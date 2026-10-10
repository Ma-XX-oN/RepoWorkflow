from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from repo_workflow.repo_ci_dispatcher import (
  RepoCiError, OPERATIONS, dispatch, validate_request,
)


REQUEST = {
  "contract_version": 1,
  "operation": "execute",
  "invocation_id": "attempt-1",
  "candidate": {
    "repository": "example/repo",
    "commit": "a" * 40,
    "base": "b" * 40,
  },
  "requirements": {"stages": []},
  "inputs": {"stages": []},
}


def request_bytes(value: dict = REQUEST) -> bytes:
  return json.dumps(value, separators=(", ", ": ")).encode("utf-8")


class RepoCiDispatcherTests(unittest.TestCase):
  def setUp(self):
    self.temp = TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    (self.root / ".ci").mkdir()

  def provider(self, source: str):
    path = self.root / "provider.py"
    path.write_text(source, encoding="utf-8")
    config = {"schema": 1, "command": [sys.executable, str(path)]}
    (self.root / ".ci" / "repo-ci.json").write_text(
      json.dumps(config), encoding="utf-8",
    )

  def success_provider(self):
    self.provider(
      "import json, sys\n"
      "raw = sys.stdin.buffer.read()\n"
      "open('received.bin', 'wb').write(raw)\n"
      "r = json.loads(raw)\n"
      "print(json.dumps({\n"
      " 'contract_version': r['contract_version'],\n"
      " 'operation': r['operation'],\n"
      " 'invocation_id': r['invocation_id'],\n"
      " 'candidate': r['candidate'],\n"
      " 'status': 'ok', 'observations': {},\n"
      " 'diagnostics': [], 'artifacts': []}))\n"
    )

  def test_all_operations_forward_exact_request_bytes(self):
    self.success_provider()
    for operation in sorted(OPERATIONS):
      with self.subTest(operation=operation):
        request = {**REQUEST, "operation": operation}
        raw = request_bytes(request)
        result = dispatch(self.root, operation, raw)
        self.assertEqual((self.root / "received.bin").read_bytes(), raw)
        self.assertEqual(result["candidate"], request["candidate"])
        self.assertEqual(result["operation"], operation)

  def test_bad_requests_do_not_invoke_provider(self):
    self.success_provider()
    cases = [
      {**REQUEST, "contract_version": True},
      {**REQUEST, "contract_version": 2},
      {**REQUEST, "candidate": {}},
      {**REQUEST, "requirements": []},
      {**REQUEST, "inputs": None},
      {**REQUEST, "operation": "publish"},
      {**REQUEST, "unexpected": 1},
    ]
    for i, candidate in enumerate(cases):
      with self.subTest(case=i):
        (self.root / "received.bin").unlink(missing_ok=True)
        with self.assertRaises(RepoCiError):
          dispatch(self.root, "execute", request_bytes(candidate))
        self.assertFalse((self.root / "received.bin").exists())

  def test_missing_configuration_fails_closed(self):
    with self.assertRaises(RepoCiError) as context:
      dispatch(self.root, "execute", request_bytes())
    self.assertEqual(context.exception.code, "prerequisite-unavailable")

  def test_malformed_json_fails_without_adapter_execution(self):
    self.success_provider()
    with self.assertRaises(RepoCiError) as context:
      dispatch(self.root, "execute", b"{")
    self.assertEqual(context.exception.code, "invalid-request")
    self.assertFalse((self.root / "received.bin").exists())

  def test_wrong_candidate_is_not_accepted(self):
    self.provider(
      "import json,sys\n"
      "r=json.loads(sys.stdin.buffer.read())\n"
      "r['candidate']['commit']='c'*40\n"
      "r.update(status='ok',observations={},diagnostics=[],artifacts=[])\n"
      "print(json.dumps(r))\n"
    )
    with self.assertRaises(RepoCiError) as context:
      dispatch(self.root, "execute", request_bytes())
    self.assertEqual(context.exception.code, "identity-mismatch")

  def test_provider_failure_not_normalized_as_test_failure(self):
    self.provider("import sys\nsys.exit(9)\n")
    with self.assertRaises(RepoCiError) as context:
      dispatch(self.root, "execute", request_bytes())
    self.assertEqual(context.exception.code, "transport-failed")

  def test_provider_semantic_error_is_preserved(self):
    self.provider(
      "import sys,json\n"
      "sys.stderr.write(json.dumps({'code':'capability-unavailable'}))\n"
      "sys.exit(2)\n"
    )
    with self.assertRaises(RepoCiError) as context:
      dispatch(self.root, "execute", request_bytes())
    self.assertEqual(context.exception.code, "capability-unavailable")

  def test_error_result_requires_semantic_diagnostic(self):
    self.provider(
      "import json,sys\n"
      "r=json.loads(sys.stdin.read())\n"
      "r.update(status='error',observations={},diagnostics=[],artifacts=[])\n"
      "print(json.dumps(r))\n"
    )
    with self.assertRaises(RepoCiError) as context:
      dispatch(self.root, "execute", request_bytes())
    self.assertEqual(context.exception.code, "internal-error")

  def test_unknown_operation_rejected_before_config_resolution(self):
    with self.assertRaises(RepoCiError) as context:
      dispatch(self.root, "merge", request_bytes())
    self.assertEqual(context.exception.code, "unsupported-operation")

  def test_invalid_command_configuration_fails_closed(self):
    (self.root / ".ci" / "repo-ci.json").write_text(
      '{"schema":1,"command":[""]}', encoding="utf-8",
    )
    with self.assertRaises(RepoCiError) as context:
      dispatch(self.root, "execute", request_bytes())
    self.assertEqual(context.exception.code, "invalid-request")


if __name__ == "__main__":
  unittest.main()
