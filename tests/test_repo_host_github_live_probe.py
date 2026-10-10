"""Specification tests for live probe cleanup and result ordering."""
from __future__ import annotations

import contextlib
import hashlib
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
    seen_issues = set()
    state = {"title": "RWF #97 SANDBOX Before",
             "pr_title": "Uncreated", "pr_state": "open"}

    def provider_read(repository, path):
      sequence.append("GET " + path)
      if path == "":
        return {"default_branch": "main"}
      if path.startswith("issues/3/comments?"):
        identity = chr(0).join([
          "owner/sandbox", "issue.comment", "acceptance-comment",
        ])
        marker = "<!-- RWF-HOST-REQUEST-V1:" + hashlib.sha256(
          identity.encode("utf-8")
        ).hexdigest() + " -->"
        return [{"id": 9, "body": "RWF probe acceptance\n" + marker}]
      if path.startswith("issues/"):
        return {"state": "open", "title": state["title"]}
      if path.startswith("git/ref/heads/"):
        return {"object": {"sha": (
          "b" * 40 if path.endswith("target") else SHA
        )}}
      if path == "pulls/17":
        return {"state": state["pr_state"],
                "title": state["pr_title"], "draft": True,
                "head": {"sha": SHA, "ref": "rwf97-sandbox-source"},
                "base": {"ref": "rwf97-sandbox-target"}}
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
          "conflict" if identity.endswith("-stale")
          or (operation == "issue.comment" and identity.endswith("-comment"))
          else "unsupported"
        )}
      if operation == "issue.update":
        status = "unchanged" if identity in seen_issues else "applied"
        seen_issues.add(identity)
        state["title"] = params["title"]
        return {"result": {"title": params["title"]},
                "status": status}
      if operation == "issue.comment":
        return {"result": {"comment_id": "9"}, "status": "unchanged"}
      if operation == "pull_request.create":
        state["pr_title"] = params["title"]
        return {"result": {"number": 17}, "status": "unchanged"}
      if operation == "pull_request.update":
        state["pr_title"] = params["title"]
        return {"result": {}, "status": "unchanged"}
      raise AssertionError("unrecognized operation " + operation)

    def cleanup(*args, **kwargs):
      sequence.append("CLOSE PR")
      if cleanup_code == 0:
        state["pr_state"] = "closed"
      return SimpleNamespace(returncode=cleanup_code)

    args = [
      "probe", "--repository", "owner/sandbox",
      "--sandbox-issue", "3", "--source-ref",
      "refs/heads/rwf97-sandbox-source", "--target-ref",
      "refs/heads/rwf97-sandbox-target", "--run-id", "acceptance",
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

  def test_remote_comment_requires_unique_exact_persisted_marker(self):
    identity = chr(0).join(["owner/sandbox", "issue.comment", "once"])
    marker = "<!-- RWF-HOST-REQUEST-V1:" + hashlib.sha256(
      identity.encode("utf-8")
    ).hexdigest() + " -->"
    valid = {"id": 13, "body": "Exact\n" + marker}
    cases = [
      [valid, valid],
      [{**valid, "body": "Tampered\n" + marker}],
      [{**valid, "id": 14}],
      [],
    ]
    for comments in cases:
      with self.subTest(comments=comments):
        with patch.object(module, "gh", return_value=comments):
          with self.assertRaises(RuntimeError):
            module.verify_remote_comment(
              "owner/sandbox", 3, "once", "13", "Exact"
            )
    with patch.object(module, "gh", return_value=[valid]):
      module.verify_remote_comment("owner/sandbox", 3, "once", "13", "Exact")

  def test_remote_comment_reads_beyond_first_hundred(self):
    identity = chr(0).join(["owner/sandbox", "issue.comment", "once"])
    marker = "<!-- RWF-HOST-REQUEST-V1:" + hashlib.sha256(
      identity.encode("utf-8")
    ).hexdigest() + " -->"
    pages = [
      [{"id": i, "body": "Unrelated"} for i in range(100)],
      [{"id": 1001, "body": "Exact\n" + marker}],
    ]
    with patch.object(module, "gh", side_effect=pages) as get:
      module.verify_remote_comment(
        "owner/sandbox", 3, "once", "1001", "Exact"
      )
    self.assertEqual(get.call_count, 2)
    self.assertIn("page=2", get.call_args.args[1])

  def test_pass_only_after_provider_cleanup_verified(self):
    calls, output = self.run_probe()
    self.assertIn("CLOSE PR", calls)
    self.assertIn("GET pulls/17", calls)
    result = json.loads(output)
    self.assertEqual(result["result"], "PASS")
    self.assertTrue(result["cleanup_verified"])

  def test_production_repo_and_non_sandbox_refs_fail_before_api(self):
    cases = [
      ["--repository", "Ma-XX-oN/RepoWorkflow"],
      ["--source-ref", "refs/heads/main"],
    ]
    original = [
      "probe", "--repository", "owner/sandbox",
      "--sandbox-issue", "3", "--source-ref",
      "refs/heads/rwf97-sandbox-source",
      "--target-ref", "refs/heads/rwf97-sandbox-target",
      "--run-id", "acceptance",
    ]
    for replacement in cases:
      with self.subTest(replacement=replacement):
        args = original.copy()
        index = args.index(replacement[0])
        args[index + 1] = replacement[1]
        with patch.object(sys, "argv", args):
          with patch.object(module, "gh") as get:
            with patch.object(module, "invoke") as invoke:
              with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                  module.main()
              self.assertEqual(caught.exception.code, 2)
              get.assert_not_called()
              invoke.assert_not_called()

  def test_cleanup_failure_has_no_success_record(self):
    calls, output = self.run_probe(cleanup_code=1)
    self.assertIn("CLOSE PR", calls)
    self.assertEqual(output, "")


if __name__ == "__main__":
  unittest.main()
