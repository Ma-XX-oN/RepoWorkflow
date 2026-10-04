from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.relationship_store import (
  RelationshipStore,
  RelationshipStoreError,
)
from repo_workflow.relationships import RelationshipGraph
from repo_workflow.state_store import WriterIdentity


def graph(dependencies=None):
  if dependencies is None:
    dependencies = []
  return RelationshipGraph.from_json_value({
    "schema_version": 2,
    "issues": {
      "10": {
        "umbrella": "1",
        "shared_umbrellas": ["50"],
        "depends_on": dependencies,
        "umbrella_depends_on": ["40"],
        "parent": "issue-7",
      },
      **({
        "7": {
          "umbrella": "1",
          "shared_umbrellas": [],
          "depends_on": [],
          "umbrella_depends_on": [],
          "parent": "main",
        },
      } if "7" in dependencies else {}),
    },
  })


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

  def test_create_and_read_round_trip_all_relationship_types(self):
    created = self.store.create(graph(["7"]), self.writer)
    read = self.store.read()

    self.assertEqual(created, read)
    self.assertEqual(read.revision, 0)
    issue = read.graph.issue("10")
    self.assertEqual(issue.umbrella, "1")
    self.assertEqual(issue.shared_umbrellas, ("50",))
    self.assertEqual(issue.depends_on, ("7",))
    self.assertEqual(issue.umbrella_depends_on, ("40",))
    self.assertEqual(issue.parent, "issue-7")

  def test_direct_dependencies_are_deterministic(self):
    self.store.create(graph(["7"]), self.writer)

    self.assertEqual(self.store.direct_dependencies(10), ("7",))

  def test_replace_uses_cas_and_preserves_prior_on_stale_write(self):
    initial = self.store.create(graph(), self.writer)
    current = self.store.replace(initial.revision, graph(["7"]), self.writer)

    with self.assertRaisesRegex(RelationshipStoreError, "stale record revision"):
      self.store.replace(initial.revision, graph(), self.writer)

    self.assertEqual(self.store.read(), current)

  def test_missing_graph_fails_closed(self):
    with self.assertRaisesRegex(RelationshipStoreError, "record is missing"):
      self.store.read()

  def test_malformed_graph_fails_closed(self):
    path = self.repo / ".repoworkflow/state/relationships/graph.json"
    path.parent.mkdir(parents=True)
    path.write_text(
      '{"schema_version": 2, "key": "relationships/graph", '
      '"revision": 0, "previous_revision": null, '
      '"writer_id": "agent", "session_id": "session", '
      '"value": {"schema_version": 99, "issues": {}}}\n',
      encoding="utf-8",
    )

    with self.assertRaisesRegex(
      RelationshipStoreError,
      "unsupported relationship schema version",
    ):
      self.store.read()

  def test_unknown_issue_query_fails_explicitly(self):
    self.store.create(graph(), self.writer)

    with self.assertRaisesRegex(RelationshipStoreError, "unknown issue"):
      self.store.issue(99)

  def test_invalid_graph_cannot_replace_authoritative_graph(self):
    current = self.store.create(graph(["7"]), self.writer)
    invalid = RelationshipGraph(issues={
      "10": current.graph.issue("10"),
    })

    with self.assertRaises(RelationshipStoreError):
      self.store.replace(current.revision, invalid, self.writer)

    self.assertEqual(self.store.read(), current)


if __name__ == "__main__":
  unittest.main()
