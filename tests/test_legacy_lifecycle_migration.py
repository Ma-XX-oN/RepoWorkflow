"""Independent durable schema-1/schema-2 lifecycle upgrade acceptance for #583."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.lifecycle_store import IssueLifecycle, LifecycleStore
from repo_workflow.state_store import WriterIdentity


def legacy_value(issue, count, schema):
  old = [
    {"sequence": 0, "transition": "start",
     "from": "unstarted", "to": "active", "candidate": "old"},
    {"sequence": 1, "transition": "accept",
     "from": "active", "to": "accepted", "candidate": "old"},
  ]
  result = {
    "schema_version": schema,
    "issue": str(issue),
    "state": ("unstarted", "active", "accepted")[count],
    "dependency_satisfied": False,
    "relationship_revision": None if count == 0 else 0,
    "history": old[:count],
  }
  if schema == 2:
    result["high_risk_aliases"] = ["graph-renderer"]
  return result


class LegacyLifecycleUpgradeAcceptance(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    subprocess.run(["git", "init"], cwd=self.root, check=True,
                   capture_output=True)
    self.writer = WriterIdentity("agent", "session")
    self.lifecycle = LifecycleStore(self.root)

  def tearDown(self):
    self.temp.cleanup()

  def test_schema_one_first_write_is_durable_schema_three(self):
    value = legacy_value(1, 0, 1)
    self.lifecycle.records.create("issues/1/lifecycle", value, self.writer)
    before = self.lifecycle.read(1)
    self.assertEqual(before.revision, 0)
    self.assertEqual(before.lifecycle.state, "not_started")
    self.assertEqual(before.lifecycle.history, ())
    updated = self.lifecycle.transition(
      1, "start", "new", 0, self.writer, before.revision,
    )
    self.assertEqual(updated.revision, 1)
    self.assertEqual(updated.lifecycle.state, "active")
    self.assertEqual(updated.lifecycle.legacy_event_count, 0)
    self.assertEqual(self.lifecycle.read(1), updated)
    raw = self.lifecycle.records.read("issues/1/lifecycle")
    self.assertEqual(raw["value"]["schema_version"], 3)
    self.assertEqual(raw["revision"], 1)
    self.assertEqual(len(raw["value"]["history"]), 1)

  def test_repeated_migration_roundtrip_has_no_spurious_revision(self):
    # L07: repeat normalized read and schema serialization without writes.
    issue = 99
    key = f"issues/{issue}/lifecycle"
    self.lifecycle.records.create(
      key, legacy_value(issue, 1, 2), self.writer,
    )
    original = self.lifecycle.read(issue)
    self.assertEqual(original.revision, 0)
    path = self.root / ".repoworkflow/state/issues/99/lifecycle.json"
    before = path.read_bytes()
    for _ in range(5):
      self.assertEqual(self.lifecycle.read(issue), original)
      self.assertEqual(path.read_bytes(), before)
    upgraded = self.lifecycle.set_high_risk_aliases(
      issue, ("graph-renderer",), self.writer, original.revision,
    )
    self.assertEqual(upgraded.revision, 1)
    after = path.read_bytes()
    for _ in range(5):
      normalized = IssueLifecycle.from_json_value(
        upgraded.lifecycle.to_json_value(),
      )
      self.assertEqual(normalized, upgraded.lifecycle)
      self.assertEqual(LifecycleStore(self.root).read(issue), upgraded)
      self.assertEqual(self.lifecycle.records.read(key)["revision"], 1)
      self.assertEqual(path.read_bytes(), after)
    self.assertEqual(len(upgraded.lifecycle.history), 1)
    self.assertEqual(upgraded.lifecycle.legacy_event_count, 1)

  def test_schema_two_zero_one_many_upgrade_preserves_every_event(self):
    for count in (0, 1, 2):
      with self.subTest(legacy_count=count):
        issue = count + 1
        key = f"issues/{issue}/lifecycle"
        self.lifecycle.records.create(
          key, legacy_value(issue, count, 2), self.writer,
        )
        before = self.lifecycle.read(issue)
        self.assertEqual(before.revision, 0)
        self.assertEqual(before.lifecycle.legacy_event_count, count)
        self.assertEqual(len(before.lifecycle.history), count)
        self.assertEqual(
          before.lifecycle.high_risk_aliases, ("graph-renderer",),
        )
        for _ in range(3):
          self.assertEqual(self.lifecycle.read(issue), before)
        upgraded = self.lifecycle.set_high_risk_aliases(
          issue, ("graph-renderer",), self.writer, before.revision,
        )
        self.assertEqual(upgraded.revision, 1)
        self.assertEqual(upgraded.lifecycle.history, before.lifecycle.history)
        self.assertEqual(upgraded.lifecycle.legacy_event_count, count)
        self.assertEqual(self.lifecycle.read(issue), upgraded)
        raw = self.lifecycle.records.read(key)
        self.assertEqual(raw["value"]["schema_version"], 3)
        self.assertEqual(raw["value"]["legacy_event_count"], count)
        self.assertEqual(raw["value"]["history"], [
          event.to_json_value() for event in before.lifecycle.history
        ])
        self.assertEqual(
          IssueLifecycle.from_json_value(raw["value"]), upgraded.lifecycle,
        )
        event = ("start", "submit-review", "complete")[count]
        advanced = self.lifecycle.transition(
          issue, event, "old" if count == 2 else "new",
          0, self.writer, upgraded.revision,
        )
        self.assertEqual(advanced.revision, 2)
        self.assertEqual(
          advanced.lifecycle.history[:count], before.lifecycle.history,
        )
        self.assertEqual(len(advanced.lifecycle.history), count + 1)
        self.assertEqual(self.lifecycle.read(issue), advanced)
        for _ in range(3):
          self.assertEqual(self.lifecycle.read(issue), advanced)
          self.assertEqual(self.lifecycle.records.read(key)["revision"], 2)


if __name__ == "__main__":
  unittest.main()
