from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.dependency_sync import (
  DependencySyncConflict,
  DependencySyncStatus,
  sync_to_tickets,
)
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


def relation(*dependencies: int) -> IssueRelationships:
  return IssueRelationships(
    umbrella=None,
    shared_umbrellas=(),
    depends_on=tuple(str(value) for value in dependencies),
    umbrella_depends_on=(),
    parent=None,
  )


class ToTicketDependencySyncTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    RepoFixture(self.root)
    RelationshipStore(self.root).create(
      RelationshipGraph(issues={
        "2": relation(),
        "9": relation(),
        "64": relation(2, 9),
      }),
      WriterIdentity("agent", "session"),
    )

  def tearDown(self):
    self.temp.cleanup()

  @patch("repo_workflow.dependency_sync.replace_ticket_dependencies")
  @patch("repo_workflow.dependency_sync.read_ticket_dependencies")
  def test_empty_destination_is_synchronized(self, read, replace):
    read.return_value = ()
    replace.return_value = (2, 9)
    result = sync_to_tickets(self.root, {}, 64)
    self.assertEqual(result.status, DependencySyncStatus.SYNCHRONIZED)
    replace.assert_called_once_with(self.root, {}, 64, (2, 9))

  @patch("repo_workflow.dependency_sync.replace_ticket_dependencies")
  @patch("repo_workflow.dependency_sync.read_ticket_dependencies")
  def test_identical_destination_is_idempotent(self, read, replace):
    read.return_value = (2, 9)
    result = sync_to_tickets(self.root, {}, 64)
    self.assertEqual(result.status, DependencySyncStatus.MATCH)
    replace.assert_not_called()

  @patch("repo_workflow.dependency_sync.replace_ticket_dependencies")
  @patch("repo_workflow.dependency_sync.read_ticket_dependencies")
  def test_conflict_fails_without_mutation(self, read, replace):
    read.return_value = (9,)
    with self.assertRaisesRegex(DependencySyncConflict, "conflict"):
      sync_to_tickets(self.root, {}, 64)
    replace.assert_not_called()
    self.assertEqual(RelationshipStore(self.root).direct_dependencies(64), ("2", "9"))

  @patch("repo_workflow.dependency_sync.replace_ticket_dependencies")
  @patch("repo_workflow.dependency_sync.read_ticket_dependencies")
  def test_replace_changes_ticket_side_only(self, read, replace):
    read.return_value = (9, 54)
    replace.return_value = (2, 9)
    before = RelationshipStore(self.root).read()
    result = sync_to_tickets(self.root, {}, 64, replace=True)
    after = RelationshipStore(self.root).read()
    self.assertEqual(result.status, DependencySyncStatus.SYNCHRONIZED)
    self.assertEqual(after, before)

  @patch("repo_workflow.dependency_sync.read_ticket_dependencies")
  def test_provider_failure_propagates(self, read):
    read.side_effect = RuntimeError("provider failed")
    with self.assertRaisesRegex(RuntimeError, "provider failed"):
      sync_to_tickets(self.root, {}, 64)


if __name__ == "__main__":
  unittest.main()
