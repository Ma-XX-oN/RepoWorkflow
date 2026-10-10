import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class GithubTransportCliTests(unittest.TestCase):
  def test_cross_process_roundtrip_stale_candidate_and_missing_artifact(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      source = root / "source"
      source.mkdir()
      (source / "validation").write_bytes(b"PASS-untrusted-by-transport")
      candidate = {"repository": "acme/repo", "commit": "a" * 40, "base": "b" * 40}
      request = {"contract_version": 1, "operation": "publish",
                 "invocation_id": "exact-invocation", "candidate": candidate,
                 "requirements": {"artifacts": ["validation"]}}
      spec = root / "request.json"
      spec.write_text(json.dumps(request))

      def command(operation, input_dir, output_dir):
        return subprocess.run(
          [sys.executable, "-m", "repo_workflow.github_transport_cli",
           operation, "--request", str(spec), "--source", str(input_dir),
           "--destination", str(output_dir)],
          capture_output=True, text=True,
        )

      packed = root / "packed"
      self.assertEqual(command("publish", source, packed).returncode, 0)
      request["operation"] = "fetch"
      spec.write_text(json.dumps(request))
      result = root / "retrieved"
      self.assertEqual(command("fetch", packed, result).returncode, 0)
      self.assertEqual((result / "validation").read_bytes(),
                       b"PASS-untrusted-by-transport")
      request["candidate"]["base"] = "c" * 40
      spec.write_text(json.dumps(request))
      invalid = root / "invalid"
      status = command("fetch", packed, invalid)
      self.assertEqual(status.returncode, 2)
      self.assertIn("identity", status.stderr)
      self.assertFalse(invalid.exists())
      request["candidate"]["base"] = "b" * 40
      spec.write_text(json.dumps(request))
      (packed / "validation").unlink()
      status = command("fetch", packed, invalid)
      self.assertEqual(status.returncode, 2)
      self.assertFalse(invalid.exists())


if __name__ == "__main__":
  unittest.main()
