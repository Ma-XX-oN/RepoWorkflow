from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.current_work_store import CurrentWorkError, CurrentWorkStore
from repo_workflow.lifecycle_store import LifecycleStore
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


def graph():
  return RelationshipGraph.from_json_value({
    "schema_version": 1,
    "issues": {
      "1": {
        "umbrella": None,
        "shared_umbrellas": [],
        "depends_on": [],
        "umbrella_depends_on": [],
        "branch_base": "main",
        "integration_target": "main",
      },
    },
  })


class CurrentWorkStoreTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.repo = Path(self.temp.name) / "repo"
    self.repo.mkdir()
    self.fx = RepoFixture(self.repo)
    self.writer = WriterIdentity("agent-a", "session-1")
    self.store = CurrentWorkStore(self.repo)

  def tearDown(self):
    self.temp.cleanup()

  def test_missing_local_state_is_empty_and_non_authoritative(self):
    snapshot = self.store.read()

    self.assertIsNone(snapshot.revision)
    self.assertIsNone(snapshot.value.current)
    self.assertIsNone(snapshot.value.resume)
    self.assertIsNone(snapshot.value.selected_issue)

  def test_start_projection_round_trips_exact_durable_references(self):
    snapshot = self.store.project_start(1, 3, 7, self.writer, None)
    reread = self.store.read()

    self.assertEqual(reread, snapshot)
    self.assertEqual(snapshot.revision, 0)
    self.assertEqual(snapshot.value.current.issue, "1")
    self.assertEqual(snapshot.value.current.lifecycle_revision, 3)
    self.assertEqual(snapshot.value.current.relationship_revision, 7)
    self.assertIsNone(snapshot.value.resume)

  def test_abort_projection_clears_current_and_preserves_resume(self):
    started = self.store.project_start(1, 3, 7, self.writer, None)
    aborted = self.store.project_abort(
      1,
      4,
      7,
      self.writer,
      started.revision,
    )

    self.assertIsNone(aborted.value.current)
    self.assertEqual(aborted.value.resume.issue, "1")
    self.assertEqual(aborted.value.resume.lifecycle_revision, 4)
    self.assertEqual(aborted.value.selected_issue, "1")

  def test_stale_local_cas_preserves_newer_record(self):
    started = self.store.project_start(1, 3, 7, self.writer, None)
    current = self.store.project_start(
      1,
      4,
      8,
      self.writer,
      started.revision,
    )

    with self.assertRaisesRegex(CurrentWorkError, "stale current-work revision"):
      self.store.project_start(1, 5, 9, self.writer, started.revision)

    self.assertEqual(self.store.read(), current)

  def test_two_worktrees_have_distinct_current_work_records(self):
    other = Path(self.temp.name) / "other"
    subprocess.run(
      ["git", "worktree", "add", "-b", "other-worktree", str(other), "HEAD"],
      cwd=self.repo,
      check=True,
      capture_output=True,
    )
    other_store = CurrentWorkStore(other)

    self.store.project_start(1, 1, 1, self.writer, None)
    other_store.project_start(2, 2, 2, self.writer, None)

    self.assertEqual(self.store.read().value.current.issue, "1")
    self.assertEqual(other_store.read().value.current.issue, "2")
    self.assertNotEqual(self.store.records.root, other_store.records.root)

  def test_durable_reference_validation_detects_lifecycle_staleness(self):
    relationship = RelationshipStore(self.repo).create(graph(), self.writer)
    lifecycle_store = LifecycleStore(self.repo)
    lifecycle = lifecycle_store.transition(
      1,
      "start",
      "candidate",
      relationship.revision,
      self.writer,
      None,
    )
    local = self.store.project_start(
      1,
      lifecycle.revision,
      relationship.revision,
      self.writer,
      None,
    )
    self.assertEqual(self.store.read(validate_durable=True), local)

    lifecycle_store.transition(
      1,
      "abort",
      "candidate",
      relationship.revision,
      self.writer,
      lifecycle.revision,
    )

    with self.assertRaisesRegex(CurrentWorkError, "stale current lifecycle"):
      self.store.read(validate_durable=True)

  def test_durable_reference_validation_detects_relationship_staleness(self):
    relationship_store = RelationshipStore(self.repo)
    relationship = relationship_store.create(graph(), self.writer)
    lifecycle = LifecycleStore(self.repo).transition(
      1,
      "start",
      "candidate",
      relationship.revision,
      self.writer,
      None,
    )
    self.store.project_start(
      1,
      lifecycle.revision,
      relationship.revision,
      self.writer,
      None,
    )
    relationship_store.replace(
      relationship.revision,
      graph(),
      self.writer,
    )

    with self.assertRaisesRegex(CurrentWorkError, "stale current relationship"):
      self.store.read(validate_durable=True)

  def test_local_projection_does_not_advance_durable_records(self):
    relationship = RelationshipStore(self.repo).create(graph(), self.writer)
    lifecycle_store = LifecycleStore(self.repo)
    lifecycle = lifecycle_store.transition(
      1,
      "start",
      "candidate",
      relationship.revision,
      self.writer,
      None,
    )

    self.store.project_start(
      1,
      lifecycle.revision,
      relationship.revision,
      self.writer,
      None,
    )

    self.assertEqual(RelationshipStore(self.repo).read().revision, 0)
    self.assertEqual(lifecycle_store.read(1).revision, 0)


if __name__ == "__main__":
  unittest.main()
