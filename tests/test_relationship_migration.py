from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.relationship_store import (
  RelationshipStore,
  RelationshipStoreError,
)
from repo_workflow.state_store import WriterIdentity, durable_store


def run(root, *args):
  return subprocess.run(
    ["git", *args],
    cwd=root,
    text=True,
    capture_output=True,
    check=True,
  ).stdout.strip()


def legacy(branch_base, integration_target):
  return {
    "schema_version": 1,
    "issues": {
      "7": {
        "umbrella": None,
        "shared_umbrellas": [],
        "depends_on": [],
        "umbrella_depends_on": [],
        "branch_base": branch_base,
        "integration_target": integration_target,
      },
    },
  }


class RelationshipMigrationTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.repo = Path(self.temp.name) / "repo"
    self.repo.mkdir()
    run(self.repo, "init", "-b", "main")
    run(self.repo, "config", "user.email", "test@example.com")
    run(self.repo, "config", "user.name", "Test")
    run(self.repo, "commit", "--allow-empty", "-m", "root")
    self.writer = WriterIdentity("agent", "session")

  def tearDown(self):
    self.temp.cleanup()

  def put(self, value):
    durable_store(self.repo).create(
      "relationships/graph",
      value,
      self.writer,
    )

  def test_equal_fields_migrate_without_branch_mapping(self):
    self.put(legacy("main", "main"))
    snapshot = RelationshipStore(self.repo).migrate_legacy(
      {},
      self.writer,
    )
    self.assertEqual(snapshot.graph.issue(7).parent, "main")
    self.assertEqual(snapshot.revision, 1)

  def test_conflicting_fields_use_recovered_parent(self):
    run(self.repo, "checkout", "-b", "issue-7", "main")
    run(
      self.repo,
      "commit",
      "--allow-empty",
      "-m",
      "identity\n\nRWF-Branch: issue-7\nRWF-Parent: main",
    )
    self.put(legacy("wrong", "other"))
    snapshot = RelationshipStore(self.repo).migrate_legacy(
      {7: "issue-7"},
      self.writer,
    )
    self.assertEqual(snapshot.graph.issue(7).parent, "main")

  def test_conflict_without_mapping_preserves_legacy_state(self):
    value = legacy("main", "other")
    self.put(value)
    with self.assertRaises(RelationshipStoreError):
      RelationshipStore(self.repo).migrate_legacy({}, self.writer)
    record = durable_store(self.repo).read("relationships/graph")
    self.assertEqual(record["value"], value)
    self.assertEqual(record["revision"], 0)

  def test_new_reader_rejects_unmigrated_legacy_schema(self):
    self.put(legacy("main", "main"))
    with self.assertRaises(RelationshipStoreError):
      RelationshipStore(self.repo).read()


if __name__ == "__main__":
  unittest.main()
