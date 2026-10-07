from pathlib import Path
import json
import tempfile
import unittest

from repo_workflow.current_work_store import CurrentWorkStore
from repo_workflow.high_risk import HighRiskError, associate_high_risk
from repo_workflow.lifecycle_store import LifecycleStore
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from repo_workflow.test_catalogue import TestCatalogueError
from tests.support import RepoFixture


class HighRiskTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.repo = Path(self.temp.name) / "repo"
    self.repo.mkdir()
    self.fx = RepoFixture(self.repo)
    self.writer = WriterIdentity("agent-a", "session-1")

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

  def test_association_unions_and_sorts_aliases(self):
    result = associate_high_risk(
      self.repo,
      ["high-risk", "command-grammar"],
      self.writer,
    )
    self.assertEqual(
      result.lifecycle.high_risk_aliases,
      ("command-grammar", "high-risk"),
    )

  def test_repeated_association_is_idempotent(self):
    first = associate_high_risk(
      self.repo,
      ["command-grammar"],
      self.writer,
    )
    current_before = CurrentWorkStore(self.repo).read()
    second = associate_high_risk(
      self.repo,
      ["command-grammar"],
      self.writer,
    )
    current_after = CurrentWorkStore(self.repo).read()

    self.assertEqual(second.revision, first.revision)
    self.assertEqual(current_after.revision, current_before.revision)

  def test_changed_association_adds_without_losing_existing(self):
    associate_high_risk(
      self.repo,
      ["command-grammar"],
      self.writer,
    )
    result = associate_high_risk(
      self.repo,
      ["high-risk"],
      self.writer,
    )
    self.assertEqual(
      result.lifecycle.high_risk_aliases,
      ("command-grammar", "high-risk"),
    )

  def test_all_aliases_are_validated_before_mutation(self):
    before = LifecycleStore(self.repo).read(1)
    with self.assertRaisesRegex(TestCatalogueError, "unknown test alias"):
      associate_high_risk(
        self.repo,
        ["command-grammar", "missing"],
        self.writer,
      )
    self.assertEqual(LifecycleStore(self.repo).read(1), before)

  def test_current_work_reference_tracks_new_lifecycle_revision(self):
    result = associate_high_risk(
      self.repo,
      ["command-grammar"],
      self.writer,
    )
    current = CurrentWorkStore(self.repo).read(validate_durable=True)
    self.assertEqual(
      current.value.current.lifecycle_revision,
      result.revision,
    )
    self.assertEqual(
      current.value.cache_lifecycle_revision,
      result.revision,
    )

  def test_requires_active_current_issue(self):
    current_store = CurrentWorkStore(self.repo)
    current = current_store.read()
    current_store.replace(
      current.revision,
      current.value.empty(),
      self.writer,
    )
    with self.assertRaisesRegex(HighRiskError, "active current issue"):
      associate_high_risk(
        self.repo,
        ["command-grammar"],
        self.writer,
      )


if __name__ == "__main__":
  unittest.main()
