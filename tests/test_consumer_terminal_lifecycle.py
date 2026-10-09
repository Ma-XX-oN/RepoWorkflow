"""Black-box consumer regression terminal-tag lifecycle."""

from pathlib import Path
import json
import sys
import unittest

from repo_workflow.test_cli import run_test
from tests.test_local import LocalVerifyTests


class ConsumerTerminalLifecycle(unittest.TestCase):
  def test_real_consumer_regression_tags_prepared_commit_after_evidence(self):
    helper = LocalVerifyTests()
    td, root, fx = helper.make_consumer()
    with td:
      initial = fx.head()
      self.assertEqual(
        run_test(
          root, "regression", remote=False,
          engine_root=root / "RepoWorkflow",
        ), 0,
      )
      path = root / ".repoworkflow/validation/testResults-1.jsonl"
      record = json.loads(path.read_text().splitlines()[-1])
      self.assertEqual(record["sourceSHA"], initial)
      self.assertEqual(record["testSHA"], fx.head())
      self.assertEqual(record["testVersion"], fx.version)
      self.assertEqual(record["result"], "succeeded")
      self.assertTrue(record["reusable"])
      tag = "v" + fx.version
      self.assertEqual(
        fx._run("rev-parse", tag + "^{commit}").stdout.strip(),
        record["testSHA"],
      )
      self.assertEqual(
        fx._run("ls-remote", "--tags", "origin",
                "refs/tags/" + tag).stdout.strip(), "",
      )


  def test_real_consumer_failure_tags_exact_prepared_candidate(self):
    helper = LocalVerifyTests()
    td, root, fx = helper.make_consumer(
      validation_body="raise SystemExit(1)\n",
    )
    with td:
      self.assertEqual(
        run_test(
          root, "regression", remote=False,
          engine_root=root / "RepoWorkflow",
        ), 1,
      )
      path = root / ".repoworkflow/validation/testResults-1.jsonl"
      record = json.loads(path.read_text().splitlines()[-1])
      self.assertEqual(record["result"], "failed")
      self.assertEqual(record["testVersion"], fx.version)
      tag = "v" + fx.version + "-CI-FAIL"
      self.assertEqual(
        fx._run("rev-parse", tag + "^{commit}").stdout.strip(),
        record["testSHA"],
      )

  def test_repeated_incomplete_attempts_preserve_version_and_tag_state(self):
    helper = LocalVerifyTests()
    mismatch = "windows" if not sys.platform.startswith("win") else "linux"
    td, root, fx = helper.make_consumer(
      validation_body="raise RuntimeError('must not run')\n",
      platform=mismatch,
    )
    with td:
      versions = []
      candidates = []
      for _ in range(2):
        self.assertEqual(
          run_test(
            root, "regression", remote=False,
            engine_root=root / "RepoWorkflow",
          ), 2,
        )
        record = json.loads((
          root / ".repoworkflow/validation/testResults-1.jsonl"
        ).read_text().splitlines()[-1])
        self.assertEqual(record["result"], "incomplete")
        self.assertEqual(fx._run("tag", "--list").stdout.strip(), "")
        versions.append((root / "VERSION").read_text().strip())
        candidates.append(record["testSHA"])
      self.assertEqual(versions, [fx.version, fx.version])
      self.assertEqual(candidates[0], candidates[1])

  def test_real_consumer_incomplete_creates_no_terminal_tag(self):
    helper = LocalVerifyTests()
    mismatch = "windows" if not sys.platform.startswith("win") else "linux"
    td, root, fx = helper.make_consumer(
      validation_body="raise RuntimeError('must not run')\n",
      platform=mismatch,
    )
    with td:
      result = run_test(
        root, "regression", remote=False,
        engine_root=root / "RepoWorkflow",
      )
      path = root / ".repoworkflow/validation/testResults-1.jsonl"
      record = json.loads(path.read_text().splitlines()[-1])
      self.assertEqual(record["result"], "incomplete")
      self.assertEqual(result, 2)
      self.assertEqual(fx._run("tag", "--list").stdout.strip(), "")


if __name__ == "__main__":
  unittest.main()
