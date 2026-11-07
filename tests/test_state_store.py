import json
import multiprocessing
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from repo_workflow.state_store import (
  JsonRecordStore,
  StateStoreError,
  WriterIdentity,
  clone_local_store,
  durable_store,
)


def _race_replace(root: str, barrier, writer_id: str, queue) -> None:
  store = JsonRecordStore(Path(root))
  barrier.wait()
  try:
    result = store.replace(
      "graph", 0, {"winner": writer_id}, WriterIdentity(writer_id, "run")
    )
    queue.put(("ok", writer_id, result["revision"]))
  except StateStoreError as error:
    queue.put(("error", writer_id, str(error)))


class StateStoreTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name)
    self.store = JsonRecordStore(self.root / "records")
    self.writer = WriterIdentity("agent-a", "session-1")

  def tearDown(self):
    self.temp.cleanup()

  def test_create_and_replace_preserve_revision_provenance(self):
    zero = self.store.create("graph", {"items": []}, self.writer)
    one = self.store.replace(
      "graph", 0, {"items": [1]}, WriterIdentity("agent-b", "session-2")
    )

    self.assertEqual(zero["revision"], 0)
    self.assertIsNone(zero["previous_revision"])
    self.assertEqual(one["revision"], 1)
    self.assertEqual(one["previous_revision"], 0)
    self.assertEqual(one["writer_id"], "agent-b")
    self.assertEqual(one["session_id"], "session-2")
    self.assertEqual(self.store.read("graph"), one)

  def test_stale_replace_fails_without_mutation(self):
    self.store.create("graph", {"value": 0}, self.writer)
    current = self.store.replace("graph", 0, {"value": 1}, self.writer)

    with self.assertRaisesRegex(StateStoreError, "stale record revision"):
      self.store.replace("graph", 0, {"value": 2}, self.writer)

    self.assertEqual(self.store.read("graph"), current)

  def test_two_processes_racing_same_revision_have_one_winner(self):
    self.store.create("graph", {"winner": None}, self.writer)
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    queue = context.Queue()
    processes = [
      context.Process(
        target=_race_replace,
        args=(str(self.store.root), barrier, writer, queue),
      )
      for writer in ("agent-b", "agent-c")
    ]
    for process in processes:
      process.start()
    results = [queue.get(timeout=10) for _ in processes]
    for process in processes:
      process.join(timeout=10)
      self.assertEqual(process.exitcode, 0)

    winners = [result for result in results if result[0] == "ok"]
    losers = [result for result in results if result[0] == "error"]
    self.assertEqual(len(winners), 1)
    self.assertEqual(len(losers), 1)
    self.assertIn("stale record revision", losers[0][2])
    self.assertEqual(self.store.read("graph")["writer_id"], winners[0][1])

  def test_independent_keys_advance_independently(self):
    self.store.create("a", {"value": 0}, self.writer)
    self.store.create("b", {"value": 0}, self.writer)
    a = self.store.replace("a", 0, {"value": 1}, self.writer)

    self.assertEqual(a["revision"], 1)
    self.assertEqual(self.store.read("b")["revision"], 0)

  def test_malformed_identity_and_payload_fail_closed(self):
    with self.assertRaises(StateStoreError):
      WriterIdentity("", "session")
    with self.assertRaises(StateStoreError):
      WriterIdentity("agent", "bad session")
    with self.assertRaisesRegex(StateStoreError, "JSON-serializable"):
      self.store.create("bad", {"value": float("nan")}, self.writer)
    self.assertFalse((self.store.root / "bad.json").exists())

  def test_failed_atomic_replace_preserves_prior_record(self):
    current = self.store.create("graph", {"value": 0}, self.writer)
    import repo_workflow.state_store as module

    def fail_replace(source, target):
      raise OSError("injected publication failure")

    with mock.patch.object(module.os, "replace", side_effect=fail_replace):
      with self.assertRaisesRegex(OSError, "injected publication failure"):
        self.store.replace("graph", 0, {"value": 1}, self.writer)

    self.assertEqual(self.store.read("graph"), current)
    self.assertEqual(list(self.store.root.glob("*.tmp")), [])

  def test_invalid_authoritative_record_fails_closed(self):
    path = self.store.root / "graph.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"schema_version": 99}\n', encoding="utf-8")

    with self.assertRaises(StateStoreError):
      self.store.read("graph")

  def test_durable_and_clone_local_placement_are_distinct(self):
    repo = self.root / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    durable = durable_store(repo)
    local = clone_local_store(repo)

    self.assertEqual(durable.root, (repo / ".repoworkflow" / "state").resolve())
    self.assertNotEqual(local.root, durable.root)
    self.assertIn("repoworkflow", local.root.parts)

  def test_relative_alias_and_foreign_repository_are_distinct(self):
    repo = self.root / "repo"
    foreign = self.root / "foreign"
    for root in (repo, foreign):
      root.mkdir()
      subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)

    alias = repo / ".." / "repo"
    canonical = durable_store(repo)
    aliased = durable_store(alias)
    other = durable_store(foreign)
    self.assertEqual(aliased.root, canonical.root)
    self.assertNotEqual(other.root, canonical.root)
    self.assertNotEqual(clone_local_store(alias).root, canonical.root)

    canonical.create("marker", {"repository": "repo"}, self.writer)
    self.assertEqual(aliased.read("marker"), canonical.read("marker"))
    with self.assertRaisesRegex(StateStoreError, "record is missing"):
      other.read("marker")

  def test_symlinked_root_alias_and_external_record_are_safe(self):
    repo = self.root / "real"
    repo.mkdir()
    alias = self.root / "alias"
    try:
      alias.symlink_to(repo, target_is_directory=True)
    except OSError as error:
      if isinstance(error, PermissionError) or getattr(error, "winerror", None) == 1314:
        self.skipTest("directory symlink permission unavailable")
      raise

    canonical = durable_store(repo)
    aliased = durable_store(alias)
    self.assertEqual(aliased.root, canonical.root)
    canonical.create("safe", {"origin": "real"}, self.writer)
    self.assertEqual(aliased.read("safe"), canonical.read("safe"))

    outside = self.root / "outside.json"
    outside.write_text("untouched", encoding="utf-8")
    escape = canonical.root / "escape.json"
    escape.parent.mkdir(parents=True, exist_ok=True)
    escape.symlink_to(outside)
    with self.assertRaisesRegex(StateStoreError, "record key escapes store"):
      aliased.create("escape", {}, self.writer)
    self.assertEqual(outside.read_text(encoding="utf-8"), "untouched")

  def test_key_cannot_escape_store(self):
    for key in ("../outside", "/absolute", "a/../b", "A"):
      with self.subTest(key=key):
        with self.assertRaises(StateStoreError):
          self.store.create(key, {}, self.writer)


if __name__ == "__main__":
  unittest.main()
