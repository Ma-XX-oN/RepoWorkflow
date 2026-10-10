"""Specification tests for live probe cleanup and result ordering."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts" / "probe-repo-host-github.py"
spec = importlib.util.spec_from_file_location("issue97_live_probe", PROBE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SHA = "a" * 40


class LiveProbeCleanupTests(unittest.TestCase):
  def run_probe(self, cleanup_code=0):
    sequence = []

    def provider_read(repository, path):
      sequence.append("GET " + path)
      if path.startswith("issues/"):
        return {"state": "open", "title": "Before"}
      if path.startswith("git/ref/heads/"):
        return {"object": {"sha": SHA}}
      if path == "pulls/17":
        return {"state": "closed"}
      raise AssertionError("unexpected provider read " + path)

    def adapter(repository, operation, identity, params, permitted=True):
      sequence.append(operation)
      if operation == "capabilities":
        return {"result": {"operations": {
          "issue.update": True, "issue.comment": True,
          "pull_request.create": True, "pull_request.update": True,
        }}}
      if not permitted:
        return {"error": (
          "conflict" if identity.endswith("-stale") else "unsupported"
        )}
      if operation == "issue.update":
        return {"result": {"title": params["title"]},
                "status": "applied"}
      if operation == "issue.comment":
        return {"result": {"comment_id": "9"}, "status": "unchanged"}
      if operation == "pull_request.create":
        return {"result": {"number": 17}, "status": "unchanged"}
      if operation == "pull_request.update":
        return {"result": {}, "status": "unchanged"}
      raise AssertionError("unrecognized operation " + operation)

    def cleanup(*args, **kwargs):
      sequence.append("CLOSE PR")
      return SimpleNamespace(returncode=cleanup_code)

    args = [
      "probe", "--repository", "owner/sandbox",
      "--sandbox-issue", "3", "--source-ref", "refs/heads/source",
      "--target-ref", "refs/heads/target", "--run-id", "acceptance",
    ]
    output = io.StringIO()
    with patch.object(sys, "argv", args):
      with patch.object(module, "gh", side_effect=provider_read):
        with patch.object(module, "invoke", side_effect=adapter):
          with patch.object(module.subprocess, "run", side_effect=cleanup):
            with contextlib.redirect_stdout(output):
              if cleanup_code:
                with self.assertRaisesRegex(
                  RuntimeError, "temporary PR close failed"
                ):
                  module.main()
              else:
                self.assertEqual(module.main(), 0)
    return sequence, output.getvalue()

  def test_pass_only_after_provider_cleanup_verified(self):
    calls, output = self.run_probe()
    self.assertIn("CLOSE PR", calls)
    self.assertIn("GET pulls/17", calls)
    result = json.loads(output)
    self.assertEqual(result["result"], "PASS")
    self.assertTrue(result["cleanup_verified"])

  def test_cleanup_failure_has_no_success_record(self):
    calls, output = self.run_probe(cleanup_code=1)
    self.assertIn("CLOSE PR", calls)
    self.assertEqual(output, "")


if __name__ == "__main__":
  unittest.main()
