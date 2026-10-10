from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import subprocess
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

  def test_stage_cardinality_and_opaque_arguments_round_trip(self):
    self.success_provider()
    for stages in ([], ["unit"], ["unit", "integration", "security"]):
      with self.subTest(stages=stages):
        request = {
          **REQUEST,
          "requirements": {"stages": stages, "artifacts": []},
          "inputs": {
            "stages": stages,
            "opaque_provider_hint": {"must_not_select_adapter": True},
          },
        }
        raw = request_bytes(request)
        response = dispatch(self.root, "execute", raw)
        self.assertEqual(response["status"], "ok")
        self.assertEqual((self.root / "received.bin").read_bytes(), raw)

  def test_wrong_operation_and_invocation_are_rejected(self):
    self.provider(
      "import json,sys\\n"
      "r=json.loads(sys.stdin.read())\\n"
      "r={k:r[k] for k in ('contract_version','operation',\\n"
      " 'invocation_id','candidate')}\\n"
      "r['invocation_id']='different'\\n"
      "r.update(status='ok',observations={},diagnostics=[],artifacts=[])\\n"
      "print(json.dumps(r))\\n"
    )
    with self.assertRaises(RepoCiError) as context:
      dispatch(self.root, "execute", request_bytes())
    self.assertEqual(context.exception.code, "identity-mismatch")

  def test_invalid_response_status_fails_normalized(self):
    self.provider(
      "import json,sys\\n"
      "r=json.loads(sys.stdin.read())\\n"
      "r={k:r[k] for k in ('contract_version','operation',\\n"
      " 'invocation_id','candidate')}\\n"
      "r.update(status={},observations={},diagnostics=[],artifacts=[])\\n"
      "print(json.dumps(r))\\n"
    )
    with self.assertRaises(RepoCiError) as context:
      dispatch(self.root, "execute", request_bytes())
    self.assertEqual(context.exception.code, "internal-error")

  def test_structured_error_result_is_forwarded(self):
    self.provider(
      "import json,sys\\n"
      "r=json.loads(sys.stdin.read())\\n"
      "r={k:r[k] for k in ('contract_version','operation',\\n"
      " 'invocation_id','candidate')}\\n"
      "r.update(status='error',observations={},\\n"
      " diagnostics=[{'code':'capability-unavailable'}],artifacts=[])\\n"
      "print(json.dumps(r))\\n"
    )
    result = dispatch(self.root, "execute", request_bytes())
    self.assertEqual(result["status"], "error")
    self.assertEqual(
      result["diagnostics"][0]["code"], "capability-unavailable",
    )

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
      "r={k:r[k] for k in ('contract_version','operation',\n"
      " 'invocation_id','candidate')}\n"
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
      "r={k:r[k] for k in ('contract_version','operation',\n"
      " 'invocation_id','candidate')}\n"
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

  @unittest.skipUnless(os.name == "posix", "POSIX executable entrypoint")
  def test_executable_repo_ci_entrypoint(self):
    self.success_provider()
    script = Path(__file__).resolve().parents[1] / "repo-ci"
    self.assertTrue(bool(script.stat().st_mode & 0o111))
    process = subprocess.run(
      [str(script), "execute"],
      cwd=self.root,
      input=request_bytes(),
      capture_output=True,
      check=False,
    )
    self.assertEqual(process.returncode, 0, process.stderr.decode())
    self.assertEqual(json.loads(process.stdout)["status"], "ok")
    self.assertEqual(
      (self.root / "received.bin").read_bytes(), request_bytes(),
    )

  def test_cli_entrypoint_preserves_exact_input(self):
    self.success_provider()
    root = Path(__file__).resolve().parents[1]
    process = subprocess.run(
      [sys.executable, str(root / "repo_workflow.py"),
       "--root", str(self.root), "repo-ci", "execute"],
      input=request_bytes(), capture_output=True, check=False,
    )
    self.assertEqual(process.returncode, 0, process.stderr.decode())
    result = json.loads(process.stdout)
    self.assertEqual(result["candidate"], REQUEST["candidate"])
    self.assertEqual(
      (self.root / "received.bin").read_bytes(), request_bytes(),
    )

  def test_duplicate_json_key_rejected_without_execution(self):
    self.success_provider()
    raw = request_bytes().replace(
      b'"operation": "execute",',
      b'"operation": "execute", "operation": "execute",',
    )
    with self.assertRaises(RepoCiError):
      dispatch(self.root, "execute", raw)
    self.assertFalse((self.root / "received.bin").exists())

  def test_nonstandard_json_rejected_before_execution(self):
    self.success_provider()
    raw = request_bytes().replace(b'"stages": []', b'"stages": [NaN]')
    with self.assertRaises(RepoCiError):
      dispatch(self.root, "execute", raw)
    self.assertFalse((self.root / "received.bin").exists())

  def test_invalid_command_configuration_fails_closed(self):
    (self.root / ".ci" / "repo-ci.json").write_text(
      '{"schema":1,"command":[""]}', encoding="utf-8",
    )
    with self.assertRaises(RepoCiError) as context:
      dispatch(self.root, "execute", request_bytes())
    self.assertEqual(context.exception.code, "invalid-request")


if __name__ == "__main__":
  unittest.main()
