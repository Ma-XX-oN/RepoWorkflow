from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.relationship_registration import register_issue_relationships
from repo_workflow.relationship_store import RelationshipStore, RelationshipStoreError
from repo_workflow.relationships import IssueRelationships
from repo_workflow.state_store import WriterIdentity


def relationships(*, dependencies=()):
  return IssueRelationships(
    umbrella="1",
    shared_umbrellas=("50",),
    depends_on=tuple(dependencies),
    umbrella_depends_on=("40",),
    branch_base="main",
    integration_target="main",
  )


class RelationshipRegistrationTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.repo = Path(self.temp.name) / "repo"
    self.repo.mkdir()
    subprocess.run(["git", "init"], cwd=self.repo, check=True, capture_output=True)
    self.writer = WriterIdentity("agent-a", "session-1")

  def tearDown(self):
    self.temp.cleanup()

  def test_registers_explicit_normalized_relationships(self):
    snapshot = register_issue_relationships(
      self.repo, 10, relationships(), self.writer, expected_revision=None
    )
    self.assertEqual(snapshot.revision, 0)
    self.assertEqual(RelationshipStore(self.repo).issue(10), relationships())

  def test_identical_registration_is_idempotent(self):
    first = register_issue_relationships(
      self.repo, 10, relationships(), self.writer, expected_revision=None
    )
    second = register_issue_relationships(
      self.repo, 10, relationships(), self.writer,
      expected_revision=first.revision,
    )
    self.assertEqual(second, first)
    self.assertEqual(RelationshipStore(self.repo).read().revision, 0)

  def test_conflicting_replacement_requires_current_revision(self):
    first = register_issue_relationships(
      self.repo, 10, relationships(), self.writer, expected_revision=None
    )
    replacement = IssueRelationships(
      umbrella="2",
      shared_umbrellas=(),
      depends_on=(),
      umbrella_depends_on=(),
      branch_base="issue-9",
      integration_target="main",
    )
    with self.assertRaisesRegex(RelationshipStoreError, "stale relationship"):
      register_issue_relationships(
        self.repo, 10, replacement, self.writer, expected_revision=99
      )
    updated = register_issue_relationships(
      self.repo, 10, replacement, self.writer,
      expected_revision=first.revision,
    )
    self.assertEqual(updated.revision, 1)
    self.assertEqual(RelationshipStore(self.repo).issue(10), replacement)

  def test_invalid_dependency_preserves_prior_graph(self):
    first = register_issue_relationships(
      self.repo, 10, relationships(), self.writer, expected_revision=None
    )
    with self.assertRaises(RelationshipStoreError):
      register_issue_relationships(
        self.repo, 10, relationships(dependencies=("7",)), self.writer,
        expected_revision=first.revision,
      )
    self.assertEqual(RelationshipStore(self.repo).read(), first)


if __name__ == "__main__":
  unittest.main()
