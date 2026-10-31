"""Native Python 3OS transport tests; fixtures never claim provider authority."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.done_host_transport import (
  NativeHostTransportError, bind_native_integration_host,
)
from repo_workflow.integration_host_v2 import IntegrationHostError


class NativeTransportTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.root = Path(self.tmp.name)
    (self.root / "adapters").mkdir()
    self.adapter = self.root / "adapters" / "repo-host-integration-v2.py"

  def script(self, mode="good"):
    self.adapter.write_text(
      "import json,sys\n"
      "request=json.load(sys.stdin)\n"
      + ("raise SystemExit(2)\n" if mode == "exit" else
         "print('bad json')\n" if mode == "malformed" else
         "print('diagnostic',file=sys.stderr)\n" if mode == "stderr" else
         "print(json.dumps(dict(schema_version=2,"
         "repository=request['repository'],operation=request['operation'],"
         "request_id=" + ("'foreign'" if mode == "foreign" else "request['request_id']") + ","
         "status='unchanged',result={'refs':{}})))\n"),
      encoding="utf-8",
    )

  def invoke(self):
    host = bind_native_integration_host(
      repository="Example/Sandbox", engine_root=self.root,
    )
    return host.request(
      "refs.list", "native-transport-1",
      {"prefix": "refs/heads/PRELIM-"},
    )

  def test_real_child_success_has_exact_verified_protocol(self):
    self.script()
    self.assertEqual(self.invoke(), {"refs": {}})

  def test_missing_provider_executable_fails_closed(self):
    with self.assertRaises(NativeHostTransportError):
      self.invoke()

  def test_nonzero_malformed_stderr_and_foreign_response_fail_closed(self):
    for mode in ("exit", "malformed", "stderr", "foreign"):
      with self.subTest(mode=mode):
        self.script(mode)
        with self.assertRaises((NativeHostTransportError,
                                IntegrationHostError)):
          self.invoke()

  def test_invalid_timeout_rejected_before_provider(self):
    self.script()
    for timeout in (0, -1, 121, True, "30"):
      with self.subTest(timeout=timeout):
        with self.assertRaises(NativeHostTransportError):
          bind_native_integration_host(
            repository="Example/Sandbox",
            engine_root=self.root, timeout=timeout,
          )

  def test_timeout_without_success_or_replay(self):
    self.script()
    with patch("repo_workflow.done_host_transport.subprocess.run",
               side_effect=subprocess.TimeoutExpired("python", 1)):
      with self.assertRaisesRegex(IntegrationHostError, "UNKNOWN"):
        self.invoke()


if __name__ == "__main__":
  unittest.main()
