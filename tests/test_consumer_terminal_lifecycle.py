"""Black-box consumer regression terminal-tag lifecycle."""

from pathlib import Path
import json
import sys
import unittest

from repo_workflow.test_cli import run_test
from repo_workflow.guard import GuardError
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

  def test_incomplete_retries_preserve_candidate_version_and_all_evidence(self):
    helper = LocalVerifyTests()
    mismatch = "windows" if not sys.platform.startswith("win") else "linux"
    td, root, fx = helper.make_consumer(
      validation_body="raise RuntimeError('must not run')\n",
      platform=mismatch,
    )
    with td:
      original = fx.head()
      path = root / ".repoworkflow/validation/testResults-1.jsonl"
      for attempt in range(3):
        self.assertEqual(
          run_test(
            root, "regression", remote=False,
            engine_root=root / "RepoWorkflow",
          ), 2,
        )
        records = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(len(records), attempt + 1)
        self.assertTrue(all(r["result"] == "incomplete" for r in records))
        self.assertEqual(fx.head(), original)
        self.assertEqual((root / "VERSION").read_text().strip(), fx.version)
        self.assertEqual(fx._run("tag", "--list").stdout.strip(), "")
        self.assertEqual(len({r["testSHA"] for r in records}), 1)

  def test_dirty_source_blocks_retry_preserving_canonical_records(self):
    helper = LocalVerifyTests()
    mismatch = "windows" if not sys.platform.startswith("win") else "linux"
    td, root, fx = helper.make_consumer(
      validation_body="raise RuntimeError('must not run')\n",
      platform=mismatch,
    )
    with td:
      self.assertEqual(
        run_test(
          root, "regression", remote=False,
          engine_root=root / "RepoWorkflow",
        ), 2,
      )
      before = fx.head()
      path = root / ".repoworkflow/validation/testResults-1.jsonl"
      evidence = path.read_bytes()
      (root / "source.txt").write_text("uncommitted mutation\n")
      with self.assertRaisesRegex(Exception, "dirty"):
        run_test(
          root, "regression", remote=False,
          engine_root=root / "RepoWorkflow",
        )
      self.assertEqual(fx.head(), before)
      self.assertEqual(path.read_bytes(), evidence)
      self.assertEqual(fx._run("tag", "--list").stdout.strip(), "")

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
