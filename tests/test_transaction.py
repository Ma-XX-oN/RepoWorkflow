import tempfile
import unittest
from pathlib import Path

from repo_workflow.state_store import JsonRecordStore, WriterIdentity
from repo_workflow.transaction import (
  SemanticTransactionCoordinator,
  StateReference,
  StateWrite,
  TransactionError,
)


class SemanticTransactionCoordinatorTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.store = JsonRecordStore(Path(self.temp.name) / "transactions")
    self.coordinator = SemanticTransactionCoordinator(self.store)
    self.writer = WriterIdentity("agent-a", "session-1")
    self.reads = (
      StateReference("durable", "lifecycle/187", 3, "abc"),
      StateReference("repository", "version", 8, "v1.2.3"),
    )
    self.writes = (
      StateWrite("durable", "lifecycle/187", {"state": "started"}),
      StateWrite("local", "current-work", {"issue": 187}),
    )

  def tearDown(self):
    self.temp.cleanup()

  def test_prepare_persists_declared_sets_before_publication(self):
    record = self.coordinator.prepare("tx-187", self.reads, self.writes, self.writer)

    self.assertEqual(record["value"]["status"], "prepared")
    self.assertEqual(len(record["value"]["read_set"]), 2)
    self.assertEqual(len(record["value"]["write_set"]), 2)
    self.assertEqual(self.coordinator.read("tx-187"), record)

  def test_commit_revalidates_then_marks_committed_before_materialization(self):
    observed = []

    def validate(reads):
      observed.append(("validate", reads))
      return True

    def materialize(writes):
      current = self.coordinator.read("tx-187")
      observed.append(("materialize", current["value"]["status"], writes))

    self.coordinator.prepare("tx-187", self.reads, self.writes, self.writer)
    committed = self.coordinator.commit(
      "tx-187", self.writer, validate, materialize
    )

    self.assertEqual(committed["value"]["status"], "committed")
    self.assertEqual(observed[0][0], "validate")
    self.assertEqual(observed[1][0:2], ("materialize", "committed"))

  def test_stale_prepared_transaction_aborts_without_materialization(self):
    materialized = []
    self.coordinator.prepare("tx-187", self.reads, self.writes, self.writer)

    with self.assertRaisesRegex(TransactionError, "read set is stale"):
      self.coordinator.commit(
        "tx-187",
        self.writer,
        lambda _reads: False,
        lambda writes: materialized.append(writes),
      )

    recovered = self.coordinator.read("tx-187")
    self.assertEqual(recovered["value"]["status"], "aborted")
    self.assertEqual(
      recovered["value"]["abort_reason"], "stale authoritative read set"
    )
    self.assertEqual(materialized, [])

  def test_interrupted_committed_materialization_is_replayed_idempotently(self):
    attempts = []
    self.coordinator.prepare("tx-187", self.reads, self.writes, self.writer)

    def interrupt(writes):
      attempts.append(writes)
      raise RuntimeError("interrupted")

    with self.assertRaisesRegex(RuntimeError, "interrupted"):
      self.coordinator.commit(
        "tx-187", self.writer, lambda _reads: True, interrupt
      )

    self.assertEqual(
      self.coordinator.read("tx-187")["value"]["status"], "committed"
    )
    self.coordinator.recover(
      "tx-187",
      self.writer,
      lambda _reads: self.fail("committed recovery must not revalidate"),
      lambda writes: attempts.append(writes),
    )
    self.assertEqual(len(attempts), 2)
    self.assertEqual(attempts[0], attempts[1])

  def test_recovery_never_assumes_prepared_is_committed(self):
    materialized = []
    prepared = self.coordinator.prepare(
      "tx-187", self.reads, self.writes, self.writer
    )

    recovered = self.coordinator.recover(
      "tx-187",
      self.writer,
      lambda _reads: True,
      lambda writes: materialized.append(writes),
    )

    self.assertEqual(recovered, prepared)
    self.assertEqual(recovered["value"]["status"], "prepared")
    self.assertEqual(materialized, [])

  def test_recovery_aborts_stale_prepared_transaction(self):
    self.coordinator.prepare("tx-187", self.reads, self.writes, self.writer)

    recovered = self.coordinator.recover(
      "tx-187",
      self.writer,
      lambda _reads: False,
      lambda _writes: self.fail("stale prepared state must not materialize"),
    )

    self.assertEqual(recovered["value"]["status"], "aborted")

  def test_committed_transaction_cannot_abort(self):
    self.coordinator.prepare("tx-187", self.reads, self.writes, self.writer)
    self.coordinator.commit(
      "tx-187", self.writer, lambda _reads: True, lambda _writes: None
    )

    with self.assertRaisesRegex(TransactionError, "cannot abort"):
      self.coordinator.abort("tx-187", self.writer, "late failure")

  def test_duplicate_set_members_fail_before_preparation(self):
    duplicate_reads = self.reads + (self.reads[0],)

    with self.assertRaisesRegex(TransactionError, "duplicate"):
      self.coordinator.prepare(
        "tx-187", duplicate_reads, self.writes, self.writer
      )

    with self.assertRaises(TransactionError):
      self.coordinator.read("tx-187")


if __name__ == "__main__":
  unittest.main()
