from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.relationship_registration import (
  RelationshipRegistrationError,
  register_issue_relationships,
)
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships
from repo_workflow.state_store import WriterIdentity


def relations(title="Issue", depends_on=()):
  return IssueRelationships(title, tuple(depends_on))


class RelationshipRegistrationTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.repo = Path(self.temp.name) / "repo"
    self.repo.mkdir()
    subprocess.run(["git", "init"], cwd=self.repo, check=True, capture_output=True)
    self.writer = WriterIdentity("agent-a", "session-1")

  def tearDown(self):
    self.temp.cleanup()

  def test_first_registration_creates_canonical_ticket_state(self):
    snapshot = register_issue_relationships(
      self.repo,
      7,
      relations(),
      self.writer,
    )
    self.assertEqual(RelationshipStore(self.repo).issue(7), relations())
    self.assertEqual(
      snapshot.revision,
      RelationshipStore(self.repo).read().revision,
    )

  def test_identical_registration_is_idempotent(self):
    first = register_issue_relationships(
      self.repo,
      7,
      relations(),
      self.writer,
    )
    second = register_issue_relationships(
      self.repo,
      "7",
      relations(),
      WriterIdentity("agent-a", "session-2"),
    )
    self.assertEqual(second, first)

  def test_conflicting_replacement_requires_expected_revision(self):
    register_issue_relationships(self.repo, 7, relations(), self.writer)
    with self.assertRaisesRegex(
      RelationshipRegistrationError,
      "requires expected revision",
    ):
      register_issue_relationships(
        self.repo,
        7,
        relations(title="Renamed"),
        self.writer,
      )

  def test_matching_revision_allows_atomic_replacement(self):
    first = register_issue_relationships(
      self.repo,
      7,
      relations(),
      self.writer,
    )
    changed = relations(title="Renamed")
    second = register_issue_relationships(
      self.repo,
      7,
      changed,
      self.writer,
      expected_revision=first.revision,
    )
    self.assertNotEqual(second.revision, first.revision)
    self.assertEqual(RelationshipStore(self.repo).issue(7), changed)

  def test_stale_revision_preserves_prior_state(self):
    first = register_issue_relationships(
      self.repo,
      7,
      relations(),
      self.writer,
    )
    changed = register_issue_relationships(
      self.repo,
      7,
      relations(title="First rename"),
      self.writer,
      expected_revision=first.revision,
    )
    with self.assertRaisesRegex(
      RelationshipRegistrationError,
      "stale ticket-state revision",
    ):
      register_issue_relationships(
        self.repo,
        7,
        relations(title="Second rename"),
        self.writer,
        expected_revision=first.revision,
      )
    self.assertEqual(
      RelationshipStore(self.repo).read(),
      changed,
    )

  def test_direct_dependency_must_already_be_canonical(self):
    with self.assertRaisesRegex(
      RelationshipRegistrationError,
      "unknown direct dependency 6",
    ):
      register_issue_relationships(
        self.repo,
        7,
        relations(depends_on=("6",)),
        self.writer,
      )


if __name__ == "__main__":
  unittest.main()
