"""Specification-based tests for disposable real-PR acceptance probe."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/probe-repo-host-github-pr-create.py"
spec = importlib.util.spec_from_file_location("rwf97_pr_create_probe", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ProviderCreateProbeTests(unittest.TestCase):
  def run_case(self, close_code=0):
    sequence = []
    result_state = {"state": "open"}
    sha = probe.SHA
    rid = "rwf97-321-1-create"
    marker = probe.identity("pull_request.create", rid)

    def provider(route):
      sequence.append("GET " + route)
      if route == "":
        return {"default_branch": "main"}
      if route.endswith("rwf97-sandbox-source"):
        return {"object": {"sha": sha}}
      if route.endswith("rwf97-sandbox-target"):
        return {"object": {"sha": "c" * 40}}
      if route == "pulls/7":
        return {
          "state": result_state["state"], "draft": True,
          "title": "RWF live probe rwf97-321-1",
          "body": (
            "Disposable adapter-created PR; never merge\n" +
            "<!-- RWF-HOST-REQUEST-V1:" + marker + " -->"
          ),
          "head": {"sha": sha, "ref": "rwf97-sandbox-source"},
          "base": {"ref": "rwf97-sandbox-target"},
          "user": {"login": "github-actions[bot]"},
        }
      raise AssertionError("unexpected provider route " + route)

    def adapter(request):
      suffix = request["request_id"]
      if suffix == rid:
        if request["parameters"]["title"] != (
          "RWF live probe rwf97-321-1"
        ):
          return 2, {"error": "conflict"}
        count = sequence.count("ADAPTER SAME")
        sequence.append("ADAPTER SAME")
        return 0, {
          "status": "applied" if not count else "unchanged",
          "result": {"number": 7},
        }
      if suffix.endswith("-stale-create"):
        return 2, {"error": "unauthorized"}
      raise AssertionError("unrecognized request identity")

    def cleanup(*args, **kwargs):
      sequence.append("CLOSE PR")
      if close_code == 0:
        result_state["state"] = "closed"
      return SimpleNamespace(returncode=close_code)

    with patch.dict(os.environ, {
      "GITHUB_REPOSITORY": probe.REPO,
      "GITHUB_REF": "refs/heads/main",
      "GITHUB_RUN_ID": "321",
    }):
      with patch.object(sys, "argv", ["probe", "--run-id",
                                     "rwf97-321-1"]):
        with patch.object(probe, "github", side_effect=provider):
          with patch.object(probe, "invoke", side_effect=adapter):
            with patch.object(probe, "assert_reservation") as reserve:
              with patch.object(probe.subprocess, "run",
                                side_effect=cleanup):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                  if close_code:
                    with self.assertRaisesRegex(
                      RuntimeError, "disposable PR cleanup failed"
                    ):
                      probe.main()
                  else:
                    self.assertEqual(probe.main(), 0)
                if close_code:
                  self.assertNotIn('"result": "PASS"', stdout.getvalue())
                else:
                  self.assertIn('"result": "PASS"', stdout.getvalue())
              reserve.assert_called_once()
    self.assertEqual(sequence.count("ADAPTER SAME"), 2)
    self.assertEqual(sequence.count("CLOSE PR"), 1)
    return sequence

  def test_exact_provider_state_replay_conflicts_and_cleanup(self):
    sequence = self.run_case()
    self.assertIn("GET pulls/7", sequence)

  def test_cleanup_failure_never_reports_complete_success(self):
    self.run_case(close_code=1)

  def test_production_or_non_sandbox_execution_refused(self):
    with patch.dict(os.environ, {
      "GITHUB_REPOSITORY": "Ma-XX-oN/RepoWorkflow",
      "GITHUB_REF": "refs/heads/main", "GITHUB_RUN_ID": "321",
    }):
      with patch.object(sys, "argv", ["probe", "--run-id",
                                     "rwf97-321-1"]):
        with patch.object(probe, "github") as remote:
          with self.assertRaisesRegex(RuntimeError, "not in owner"):
            probe.main()
          remote.assert_not_called()


if __name__ == "__main__":
  unittest.main()
