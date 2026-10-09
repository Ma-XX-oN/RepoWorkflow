"""Black-box consumer regression terminal-tag lifecycle."""

from pathlib import Path
import json
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


if __name__ == "__main__":
  unittest.main()
