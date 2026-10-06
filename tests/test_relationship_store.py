from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from repo_workflow.relationship_store import (
  RelationshipStore,
  RelationshipStoreError,
)
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity


def graph(title="Ten", dependencies=()):
  issues = {"10": IssueRelationships(title, tuple(dependencies))}
  if "7" in dependencies:
    issues["7"] = IssueRelationships("Seven", ())
  return RelationshipGraph(issues=issues)


class RelationshipStoreTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.repo = Path(self.temp.name) / "repo"
    self.repo.mkdir()
    subprocess.run(["git", "init"], cwd=self.repo, check=True, capture_output=True)
    self.store = RelationshipStore(self.repo)
    self.writer = WriterIdentity("agent-a", "session-1")

  def tearDown(self):
    self.temp.cleanup()

  def test_create_and_read_round_trip_ticket_state(self):
    created = self.store.create(graph(dependencies=("7",)), self.writer)
    read = self.store.read()

    self.assertEqual(created, read)
    self.assertEqual(read.graph.issue(10).title, "Ten")
    self.assertEqual(read.graph.issue(10).depends_on, ("7",))
    self.assertTrue((self.repo / ".repoworkflow/tickets.csv").is_file())

  def test_direct_dependencies_are_deterministic(self):
    self.store.create(graph(dependencies=("7",)), self.writer)
    self.assertEqual(self.store.direct_dependencies(10), ("7",))

  def test_replace_uses_content_cas_and_preserves_prior_on_stale_write(self):
    initial = self.store.create(graph(), self.writer)
    current = self.store.replace(
      initial.revision,
      graph(title="Ten renamed"),
      self.writer,
    )

    with self.assertRaisesRegex(RelationshipStoreError, "stale ticket-state"):
      self.store.replace(
        initial.revision,
        graph(title="Another"),
        self.writer,
      )

    self.assertEqual(self.store.read(), current)

  def test_missing_graph_fails_closed(self):
    with self.assertRaisesRegex(RelationshipStoreError, "record is missing"):
      self.store.read()

  def test_malformed_csv_fails_closed(self):
    path = self.repo / ".repoworkflow/tickets.csv"
    path.parent.mkdir(parents=True)
    path.write_text(
      "issue,title,dependencies\n10,Ten,99\n",
      encoding="utf-8",
    )
    with self.assertRaisesRegex(
      RelationshipStoreError,
      "unknown direct dependency",
    ):
      self.store.read()

  def test_unknown_issue_query_fails_explicitly(self):
    self.store.create(graph(), self.writer)
    with self.assertRaisesRegex(RelationshipStoreError, "unknown issue"):
      self.store.issue(99)

  def test_invalid_graph_cannot_replace_authoritative_graph(self):
    current = self.store.create(
      graph(dependencies=("7",)),
      self.writer,
    )
    invalid = RelationshipGraph(issues={
      "10": current.graph.issue("10"),
    })
    with self.assertRaises(RelationshipStoreError):
      self.store.replace(current.revision, invalid, self.writer)
    self.assertEqual(self.store.read(), current)

  def test_legacy_projection_discards_obsolete_fields(self):
    graph_path = (
      self.repo / ".repoworkflow/state/relationships/graph.json"
    )
    metadata_path = (
      self.repo / ".repoworkflow/state/issues/metadata.json"
    )
    graph_path.parent.mkdir(parents=True)
    metadata_path.parent.mkdir(parents=True)
    graph_path.write_text(json.dumps({
      "revision": 4,
      "value": {
        "schema_version": 2,
        "issues": {
          "10": {
            "umbrella": "1",
            "shared_umbrellas": ["50"],
            "depends_on": [],
            "umbrella_depends_on": ["40"],
            "parent": "main",
          },
        },
      },
    }), encoding="utf-8")
    metadata_path.write_text(json.dumps({
      "value": {
        "schema_version": 2,
        "issues": {
          "10": {
            "number": 10,
            "title": "Epic: Ten",
            "state": "open",
            "link": "https://example.invalid/10",
          },
        },
      },
    }), encoding="utf-8")

    migrated = self.store.migrate_legacy(self.writer)

    self.assertEqual(migrated.graph.issue(10).title, "Epic: Ten")
    self.assertEqual(migrated.graph.issue(10).depends_on, ())
    self.assertFalse(hasattr(migrated.graph.issue(10), "parent"))
    self.assertFalse(hasattr(migrated.graph.issue(10), "umbrella"))

  def test_legacy_migration_without_titles_fails_without_mutating_source(self):
    path = self.repo / ".repoworkflow/state/relationships/graph.json"
    path.parent.mkdir(parents=True)
    value = {
      "revision": 0,
      "value": {
        "schema_version": 2,
        "issues": {
          "10": {
            "umbrella": None,
            "shared_umbrellas": [],
            "depends_on": [],
            "umbrella_depends_on": [],
            "parent": "main",
          },
        },
      },
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    before = path.read_bytes()
    with self.assertRaisesRegex(RelationshipStoreError, "titles are missing"):
      self.store.migrate_legacy(self.writer)
    self.assertEqual(path.read_bytes(), before)
    self.assertFalse((self.repo / ".repoworkflow/tickets.csv").exists())


if __name__ == "__main__":
  unittest.main()
