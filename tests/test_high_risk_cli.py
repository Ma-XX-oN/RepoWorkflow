from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

from repo_workflow.current_work_store import CurrentWorkStore
from repo_workflow.lifecycle_store import LifecycleStore
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]


class HighRiskCliTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.repo = Path(self.temp.name) / "repo"
    self.repo.mkdir()
    self.fx = RepoFixture(self.repo)
    self.writer = WriterIdentity("setup", "setup-session")
    (self.repo / ".ci" / "tests.json").write_text(json.dumps({
      "test-harnesses": {
        "unit": {
          "command": "python",
          "layout": ["-m", "unittest", "$test"],
        },
      },
      "tests": [{
        "test-harness": "unit",
        "issue-475-high-risk": {
          "type": "regression",
          "name": "tests.test_high_risk",
        },
        "issue-456-grammar": {
          "type": "regression",
          "name": "tests.test_quantified_grammar",
        },
      }],
      "aliases": {
        "command-grammar": ["issue-456-grammar"],
        "high-risk": ["issue-475-high-risk"],
      },
    }), encoding="utf-8")

    relationship = RelationshipStore(self.repo).create(
      RelationshipGraph(issues={
        "1": IssueRelationships("Issue 1", ()),
      }),
      self.writer,
    )
    lifecycle = LifecycleStore(self.repo).transition(
      1,
      "start",
      "candidate",
      relationship.revision,
      self.writer,
      None,
    )
    CurrentWorkStore(self.repo).project_start(
      1,
      lifecycle.revision,
      relationship.revision,
      self.writer,
      None,
    )

  def tearDown(self):
    self.temp.cleanup()

  def run_rwf(self, *args):
    env = dict(os.environ)
    env["RWF_WRITER_ID"] = "cli-agent"
    env["RWF_SESSION_ID"] = "cli-session"
    return subprocess.run(
      [
        sys.executable,
        str(ROOT / "repo_workflow.py"),
        "--root",
        str(self.repo),
        *args,
      ],
      cwd=ROOT,
      env=env,
      text=True,
      capture_output=True,
    )

  def test_public_command_persists_multiple_aliases(self):
    result = self.run_rwf(
      "high-risk",
      "high-risk",
      "command-grammar",
    )
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(
      json.loads(result.stdout),
      {
        "issue": "1",
        "high_risk_aliases": ["command-grammar", "high-risk"],
      },
    )
    self.assertEqual(
      LifecycleStore(self.repo).read(1).lifecycle.high_risk_aliases,
      ("command-grammar", "high-risk"),
    )

  def test_completion_reads_aliases_from_authoritative_catalogue(self):
    result = self.run_rwf(
      "complete",
      "--",
      "high-risk",
      "",
    )
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(
      result.stdout.splitlines(),
      ["command-grammar", "high-risk"],
    )

  def test_unknown_alias_fails_without_partial_mutation(self):
    before = LifecycleStore(self.repo).read(1)
    result = self.run_rwf(
      "high-risk",
      "command-grammar",
      "missing",
    )
    self.assertEqual(result.returncode, 2)
    self.assertIn("unrecognised command", result.stderr)
    self.assertEqual(LifecycleStore(self.repo).read(1), before)

  def test_command_requires_at_least_one_section(self):
    result = self.run_rwf("high-risk")
    self.assertEqual(result.returncode, 2)
    self.assertIn("unrecognised command", result.stderr)


if __name__ == "__main__":
  unittest.main()
