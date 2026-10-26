"""RWF #721 hermetic first-use contracts: FirstUseRefreshTests."""
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


class FirstUseRefreshTests(FirstUseFixture, unittest.TestCase):
  def test_failed_lane_refresh_writes_failure_diagnostics(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)

      selected = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "203",
        "--json",
      )
      self.assertEqual(selected.returncode, 0, selected.stderr)

      set_provider_failure(env, info=None, dependency="provider unavailable")

      failed = self.run_rwf(
        root,
        env,
        "lanes",
        "view",
        "--refresh",
      )
      self.assertEqual(failed.returncode, 2)
      self.assertIn("provider unavailable", failed.stderr)

      diagnostics_dir = (
        root
        / ".git"
        / "repoworkflow"
        / "diagnostics"
        / "lanes"
      )
      records = sorted(
        diagnostics_dir.glob("lane-invocation--*.json"),
        key=lambda path: path.stat().st_mtime_ns,
      )
      self.assertGreaterEqual(len(records), 2)
      record = json.loads(records[-1].read_text(encoding="utf-8"))
      self.assertFalse(record["success"])
      self.assertEqual(record["error"], "TicketDependencyError")
      self.assertGreaterEqual(record["provider_calls"]["dependencies"], 1)

  def test_repeated_selection_extends_existing_partial_graph(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)

      first = self.run_rwf(root, env, "lanes", "select", "206", "--json")
      self.assertEqual(first.returncode, 0, first.stderr)
      self.assertEqual(json.loads(first.stdout)["closure"], ["206"])

      second = self.run_rwf(root, env, "lanes", "select", "206", "203", "--json")
      self.assertEqual(second.returncode, 0, second.stderr)
      self.assertEqual(
        json.loads(second.stdout)["closure"],
        ["201", "203", "206"],
      )

      third = self.run_rwf(root, env, "lanes", "select", "205", "218", "--json")
      self.assertEqual(third.returncode, 0, third.stderr)
      self.assertEqual(
        json.loads(third.stdout)["closure"],
        ["205", "208", "217", "218"],
      )

      rows = self.ticket_rows(root)
      self.assertEqual(
        sorted(rows, key=int),
        ["201", "203", "205", "206", "208", "217", "218"],
      )
      self.assertEqual(rows["203"]["dependencies"], "201")
      self.assertEqual(rows["205"]["dependencies"], "208")
      self.assertEqual(rows["218"]["dependencies"], "217")

  def test_select_add_remove_preserve_distinct_root_semantics(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)

      selected = self.run_rwf(root, env, "lanes", "select", "206", "--json")
      self.assertEqual(selected.returncode, 0, selected.stderr)
      self.assertEqual(json.loads(selected.stdout)["roots"], ["206"])

      added = self.run_rwf(root, env, "lanes", "select", "add", "203", "--json")
      self.assertEqual(added.returncode, 0, added.stderr)
      self.assertEqual(json.loads(added.stdout)["roots"], ["203", "206"])
      self.assertEqual(
        json.loads(added.stdout)["closure"],
        ["201", "203", "206"],
      )

      removed = self.run_rwf(root, env, "lanes", "select", "remove", "206", "--json")
      self.assertEqual(removed.returncode, 0, removed.stderr)
      self.assertEqual(json.loads(removed.stdout)["roots"], ["203"])
      self.assertEqual(json.loads(removed.stdout)["closure"], ["201", "203"])

      replaced = self.run_rwf(root, env, "lanes", "select", "205", "218", "--json")
      self.assertEqual(replaced.returncode, 0, replaced.stderr)
      self.assertEqual(json.loads(replaced.stdout)["roots"], ["205", "218"])
      self.assertEqual(
        json.loads(replaced.stdout)["closure"],
        ["205", "208", "217", "218"],
      )

  def test_cached_selection_reuses_relationships_and_add_reads_only_missing(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)

      first = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "203",
        "--json",
      )
      self.assertEqual(first.returncode, 0, first.stderr)
      self.assertEqual(self.dependency_calls(env), [203, 201])

      repeated = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "203",
        "--json",
      )
      self.assertEqual(repeated.returncode, 0, repeated.stderr)
      self.assertEqual(self.dependency_calls(env), [203, 201])

      added = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "add",
        "206",
        "--json",
      )
      self.assertEqual(added.returncode, 0, added.stderr)
      self.assertEqual(self.dependency_calls(env), [203, 201, 206])

      removed = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "remove",
        "206",
        "--json",
      )
      self.assertEqual(removed.returncode, 0, removed.stderr)
      self.assertEqual(self.dependency_calls(env), [203, 201, 206])

      restarted = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "203",
        "--json",
      )
      self.assertEqual(restarted.returncode, 0, restarted.stderr)
      self.assertEqual(self.dependency_calls(env), [203, 201, 206])

  def test_refresh_rereads_relevant_closure_only(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)

      selected = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "203",
        "--json",
      )
      self.assertEqual(selected.returncode, 0, selected.stderr)
      self.assertEqual(self.dependency_calls(env), [203, 201])

      refreshed = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "203",
        "--refresh",
        "--json",
      )
      self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
      self.assertEqual(
        self.dependency_calls(env),
        [203, 201, 201, 203],
      )
      self.assertNotIn(206, self.dependency_calls(env))

  def test_remove_refresh_excludes_removed_only_root_from_provider_scope(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)

      first = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "203",
        "--json",
      )
      self.assertEqual(first.returncode, 0, first.stderr)

      added = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "add",
        "206",
        "--json",
      )
      self.assertEqual(added.returncode, 0, added.stderr)
      before = list(self.dependency_calls(env))

      removed = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "remove",
        "206",
        "--refresh",
        "--json",
      )
      self.assertEqual(removed.returncode, 0, removed.stderr)
      self.assertEqual(json.loads(removed.stdout)["roots"], ["203"])
      self.assertEqual(
        self.dependency_calls(env)[len(before):],
        [201, 203],
      )

  def test_cached_selection_succeeds_when_dependency_provider_is_unavailable(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)

      first = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "203",
        "--json",
      )
      self.assertEqual(first.returncode, 0, first.stderr)

      set_provider_failure(env, info=None, dependency="provider unavailable")

      cached = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "203",
        "--json",
      )
      self.assertEqual(cached.returncode, 0, cached.stderr)
      self.assertEqual(json.loads(cached.stdout)["closure"], ["201", "203"])

  def test_refresh_provider_failure_preserves_graph_and_selection(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)

      first = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "203",
        "--json",
      )
      self.assertEqual(first.returncode, 0, first.stderr)
      graph_path = root / ".repoworkflow" / "tickets.csv"
      selection_path = (
        root
        / ".git"
        / "repoworkflow"
        / "lane-selection"
        / "selection.json"
      )
      graph_before = graph_path.read_text(encoding="utf-8")
      selection_before = selection_path.read_text(encoding="utf-8")

      set_provider_failure(env, info=None, dependency="provider unavailable")

      refreshed = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "203",
        "--refresh",
        "--json",
      )
      self.assertEqual(refreshed.returncode, 2)
      self.assertIn("provider unavailable", refreshed.stderr)
      self.assertEqual(
        graph_path.read_text(encoding="utf-8"),
        graph_before,
      )
      self.assertEqual(
        selection_path.read_text(encoding="utf-8"),
        selection_before,
      )

