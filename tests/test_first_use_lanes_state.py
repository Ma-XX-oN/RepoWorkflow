"""RWF #721 hermetic first-use contracts: FirstUseStateTests."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.p4_provider_fixture import (
  CLI, FIXTURE, ROOT, FirstUseFixture, provider_calls,
  set_metadata_titles, set_provider_failure, verify_provider,
)


class FirstUseStateTests(FirstUseFixture, unittest.TestCase):
  def test_existing_empty_canonical_issue_reconciles_after_provider_migration(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base, {203: [], 201: []})

      first = self.run_rwf(root, env, "lanes", "select", "203", "--json")
      self.assertEqual(first.returncode, 0, first.stderr)
      self.assertEqual(json.loads(first.stdout)["closure"], ["203"])

      state_path = Path(env["RWF_TEST_DEPS"])
      state_path.write_text(
        json.dumps({"203": [201], "201": []}),
        encoding="utf-8",
      )
      self.certify_migration(root)

      second = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "203",
        "--refresh",
        "--json",
      )
      self.assertEqual(second.returncode, 0, second.stderr)
      self.assertEqual(json.loads(second.stdout)["closure"], ["201", "203"])

      rows = self.ticket_rows(root)
      self.assertEqual(rows["203"]["dependencies"], "201")
      self.assertIn("201", rows)

  def test_existing_nonempty_dependency_conflict_fails_closed(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base, {203: [201], 201: [], 206: []})

      first = self.run_rwf(root, env, "lanes", "select", "203", "--json")
      self.assertEqual(first.returncode, 0, first.stderr)

      state_path = Path(env["RWF_TEST_DEPS"])
      state_path.write_text(
        json.dumps({"201": [], "203": [206], "206": []}),
        encoding="utf-8",
      )
      self.certify_migration(root)

      conflicted = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "203",
        "--refresh",
        "--json",
      )
      self.assertEqual(conflicted.returncode, 2)
      self.assertIn("conflict with native ticket dependencies", conflicted.stderr)

      rows = self.ticket_rows(root)
      self.assertEqual(rows["203"]["dependencies"], "201")
      self.assertNotIn("206", rows)

  def test_repository_manifest_blocks_bootstrap_until_migration_certified(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)
      migration = (
        root
        / ".repoworkflow"
        / "migrations"
        / "native-dependencies-v1.json"
      )
      migration.parent.mkdir(parents=True)
      migration.write_text("{}\n", encoding="utf-8")

      selected = self.run_rwf(root, env, "lanes", "select", "206", "--json")
      self.assertEqual(selected.returncode, 2)
      self.assertIn(
        "uncommitted migration manifest is not certified",
        selected.stderr,
      )
      self.assertNotIn("Traceback", selected.stderr)
      self.assertFalse(
        (root / ".repoworkflow" / "tickets.csv").exists()
      )

  def test_read_only_lane_failure_does_not_create_runtime_identity(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)

      listed = self.run_rwf(root, env, "lanes", "list")
      self.assertEqual(listed.returncode, 2)
      self.assertIn("lane selection is missing", listed.stderr)
      self.assertFalse(
        (root / ".git" / "repoworkflow" / "runtime-writer-id").exists()
      )

  def test_partial_explicit_identity_fails_without_synthesizing_other_half(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)
      env["RWF_WRITER_ID"] = "agent-explicit"

      selected = self.run_rwf(root, env, "lanes", "select", "206", "--json")
      self.assertEqual(selected.returncode, 2)
      self.assertIn("RWF_SESSION_ID", selected.stderr)
      self.assertFalse(
        (root / ".git" / "repoworkflow" / "runtime-writer-id").exists()
      )
      self.assertFalse((root / ".repoworkflow").exists())

  def test_explicit_agent_identity_is_preserved(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)
      env["RWF_WRITER_ID"] = "agent-explicit"
      env["RWF_SESSION_ID"] = "session-explicit"

      selected = self.run_rwf(root, env, "lanes", "select", "206", "--json")
      self.assertEqual(selected.returncode, 0, selected.stderr)

      selection_path = (
        root
        / ".git"
        / "repoworkflow"
        / "lane-selection"
        / "selection.json"
      )
      record = json.loads(selection_path.read_text(encoding="utf-8"))
      self.assertEqual(record["writer_id"], "agent-explicit")
      self.assertEqual(record["session_id"], "session-explicit")

      writer_path = root / ".git" / "repoworkflow" / "runtime-writer-id"
      self.assertFalse(writer_path.exists())

