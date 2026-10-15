"""Independent lifecycle/CSV multi-record crash recovery acceptance for #583."""

from pathlib import Path
import tempfile
import unittest

from repo_workflow.lifecycle_store import LifecycleStore
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity, durable_store
from repo_workflow.transaction import (
  SemanticTransactionCoordinator, StateReference, StateWrite,
)
from tests.support import RepoFixture


class LifecycleCsvRecoveryAcceptance(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    RepoFixture(self.root)
    self.writer = WriterIdentity("writer", "session")
    self.lifecycle = LifecycleStore(self.root)
    self.relationships = RelationshipStore(self.root)
    self.relationships.create(
      RelationshipGraph(issues={
        "1": IssueRelationships("Ticket one", ()),
      }),
      self.writer,
    )
    self.coordinator = SemanticTransactionCoordinator(durable_store(self.root))
    self.csv_before = self.relationships.path.read_bytes()

  def tearDown(self):
    self.temp.cleanup()

  def prepare(self):
    snapshot = self.relationships.read()
    return self.coordinator.prepare(
      "lifecycle-projection-one",
      (
        StateReference("lifecycle", "1", 0, "absent"),
        StateReference("relationships", "graph", snapshot.revision),
      ),
      (
        StateWrite("lifecycle", "1", {"transition": "start"}),
        StateWrite("projection", "tickets", {"refresh": True}),
      ),
      self.writer,
    )

  def materialize(self, writes, *, interrupt=False):
    self.assertEqual(len(writes), 2)
    existing = self.lifecycle.read(1)
    if existing.revision is None:
      self.lifecycle.transition(
        1, "start", "candidate", 0, self.writer, None,
      )
    else:
      self.assertEqual(existing.revision, 0)
      self.assertEqual(existing.lifecycle.state, "active")
    if interrupt:
      raise RuntimeError("crash after authoritative lifecycle mutation")
    snapshot = self.relationships.read()
    if snapshot.states is None or snapshot.states["1"].state != "active":
      self.relationships.refresh_states(self.writer)

  def test_restart_replays_partial_lifecycle_and_csv_once(self):
    # C07/C09: durable tx committed, lifecycle published, CSV not yet written.
    self.prepare()
    with self.assertRaisesRegex(RuntimeError, "crash after"):
      self.coordinator.commit(
        "lifecycle-projection-one", self.writer, lambda _reads: True,
        lambda writes: self.materialize(writes, interrupt=True),
      )
    self.assertEqual(
      self.coordinator.read("lifecycle-projection-one")["value"]["status"],
      "committed",
    )
    self.assertEqual(self.lifecycle.read(1).lifecycle.state, "active")
    self.assertEqual(self.lifecycle.read(1).revision, 0)
    self.assertEqual(self.relationships.path.read_bytes(), self.csv_before)
    restarted = SemanticTransactionCoordinator(durable_store(self.root))
    resumed = restarted.recover(
      "lifecycle-projection-one", self.writer,
      lambda _reads: self.fail("committed replay revalidated stale reads"),
      lambda writes: self.materialize(writes),
    )
    self.assertEqual(resumed["value"]["status"], "committed")
    refreshed = RelationshipStore(self.root).read()
    self.assertEqual(refreshed.states["1"].state, "active")
    self.assertEqual(refreshed.states["1"].lifecycle_revision, 0)
    csv_after = self.relationships.path.read_bytes()
    for _ in range(3):
      restarted.recover(
        "lifecycle-projection-one", self.writer,
        lambda _reads: self.fail("repeated commit must not revalidate"),
        lambda writes: self.materialize(writes),
      )
      self.assertEqual(self.lifecycle.read(1).revision, 0)
      self.assertEqual(self.relationships.path.read_bytes(), csv_after)
    self.assertEqual(RelationshipStore(self.root).read(), refreshed)

  def test_restart_aborts_stale_prepared_without_csv_mutation(self):
    # C08/C10: prepared is never completion, stale authority aborts.
    self.prepare()
    self.lifecycle.transition(
      1, "start", "other-candidate", 0, self.writer, None,
    )
    restarted = SemanticTransactionCoordinator(durable_store(self.root))
    recovered = restarted.recover(
      "lifecycle-projection-one", self.writer,
      lambda _reads: False,
      lambda _writes: self.fail("stale prepared transaction published"),
    )
    self.assertEqual(recovered["value"]["status"], "aborted")
    self.assertEqual(self.relationships.path.read_bytes(), self.csv_before)
    self.assertEqual(self.lifecycle.read(1).revision, 0)
    self.assertEqual(
      restarted.recover(
        "lifecycle-projection-one", self.writer,
        lambda _reads: self.fail("aborted recovery revalidated"),
        lambda _writes: self.fail("aborted recovery published"),
      ),
      recovered,
    )


if __name__ == "__main__":
  unittest.main()
