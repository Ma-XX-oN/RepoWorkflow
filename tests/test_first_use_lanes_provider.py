"""RWF #721 hermetic first-use contracts: FirstUseProviderTests."""
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


class FirstUseProviderTests(FirstUseFixture, unittest.TestCase):
  def test_lane_list_refresh_is_metadata_only_and_source_accurate(self):
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

      graph_path = root / ".repoworkflow" / "tickets.csv"
      selection_path = (
        root / ".git/repoworkflow/lane-selection/selection.json"
      )
      metadata_cache_path = (
        root / ".repoworkflow/state/issues/metadata.json"
      )
      graph_before = graph_path.read_bytes()
      selection_before = selection_path.read_bytes()

      plain = self.run_rwf(root, env, "lanes", "list")
      self.assertEqual(plain.returncode, 0, plain.stderr)
      self.assertIn("#203  Root 203", plain.stdout)

      diagnostics_dir = (
        root / ".git/repoworkflow/diagnostics/lanes"
      )
      records = sorted(
        diagnostics_dir.glob("lane-invocation--*.json"),
        key=lambda path: path.stat().st_mtime_ns,
      )
      plain_record = json.loads(records[-1].read_text(encoding="utf-8"))
      self.assertEqual(plain_record["provider_calls"], {})
      self.assertEqual(plain_record["cache_hits"]["metadata"], 2)
      self.assertNotIn("relationships", plain_record["cache_hits"])

      metadata_path = Path(env["RWF_TEST_META"])
      metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
      metadata["203"]["title"] = "Updated Root 203"
      metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

      set_provider_failure(env, info=None, dependency="dependency provider must not be used")

      refreshed = self.run_rwf(
        root,
        env,
        "lanes",
        "list",
        "--refresh",
      )
      self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
      self.assertIn("#203  Updated Root 203", refreshed.stdout)
      self.assertIn("Refreshing metadata:", refreshed.stderr)
      self.assertNotIn("Refreshing dependencies:", refreshed.stderr)
      self.assertNotIn("dependency provider must not be used", refreshed.stderr)
      self.assertNotEqual(graph_path.read_bytes(), graph_before)
      self.assertEqual(selection_path.read_bytes(), selection_before)
      self.assertEqual(
        self.ticket_rows(root)["203"]["title"],
        "Updated Root 203",
      )

      cached = json.loads(metadata_cache_path.read_text(encoding="utf-8"))
      self.assertNotIn("title", cached["value"]["issues"]["203"])
      records = sorted(
        diagnostics_dir.glob("lane-invocation--*.json"),
        key=lambda path: path.stat().st_mtime_ns,
      )
      refresh_record = json.loads(records[-1].read_text(encoding="utf-8"))
      self.assertEqual(refresh_record["provider_calls"], {"metadata": 2})
      self.assertNotIn("relationships", refresh_record["cache_hits"])
      self.assertNotIn("relationships", refresh_record["cache_misses"])

  def test_lane_list_refresh_metadata_failure_rolls_back_all_semantic_state(self):
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

      graph_path = root / ".repoworkflow" / "tickets.csv"
      selection_path = (
        root / ".git/repoworkflow/lane-selection/selection.json"
      )
      metadata_path = root / ".repoworkflow/state/issues/metadata.json"
      before = {
        "graph": graph_path.read_bytes(),
        "selection": selection_path.read_bytes(),
        "metadata": metadata_path.read_bytes(),
      }

      set_provider_failure(env, info="metadata unavailable", dependency="dependency provider must not be used")

      refreshed = self.run_rwf(
        root,
        env,
        "lanes",
        "list",
        "--refresh",
      )
      self.assertEqual(refreshed.returncode, 2)
      self.assertIn("metadata unavailable", refreshed.stderr)
      self.assertNotIn("dependency provider must not be used", refreshed.stderr)
      self.assertEqual(graph_path.read_bytes(), before["graph"])
      self.assertEqual(selection_path.read_bytes(), before["selection"])
      self.assertEqual(metadata_path.read_bytes(), before["metadata"])

  def test_lane_list_refresh_updates_cached_issue_metadata(self):
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
      dependency_calls_before = list(self.dependency_calls(env))

      set_metadata_titles(env, {201: "Leaf 201 refreshed", 203: "Root 203 refreshed"})
      set_provider_failure(env, info=None, dependency="dependency provider must not be used")

      refreshed = self.run_rwf(
        root,
        env,
        "lanes",
        "list",
        "--refresh",
      )
      self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
      self.assertIn("#201  Leaf 201 refreshed", refreshed.stdout)
      self.assertIn("#203  Root 203 refreshed", refreshed.stdout)
      self.assertEqual(self.dependency_calls(env), dependency_calls_before)

      offline = self.run_rwf(root, env, "lanes", "list")
      self.assertEqual(offline.returncode, 0, offline.stderr)
      self.assertIn("#203  Root 203 refreshed", offline.stdout)

  def test_lane_list_and_view_are_offline_until_explicit_refresh(self):
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

      set_provider_failure(env, info="provider unavailable", dependency="provider unavailable")

      listed = self.run_rwf(root, env, "lanes", "list")
      self.assertEqual(listed.returncode, 0, listed.stderr)
      self.assertIn("#201  Leaf 201", listed.stdout)
      self.assertIn("#203  Root 203", listed.stdout)

      viewed = self.run_rwf(root, env, "lanes", "view")
      self.assertEqual(viewed.returncode, 0, viewed.stderr)
      self.assertIn("A201", viewed.stdout)
      self.assertIn("A203", viewed.stdout)

      refreshed = self.run_rwf(
        root,
        env,
        "lanes",
        "view",
        "--refresh",
      )
      self.assertEqual(refreshed.returncode, 2)
      self.assertIn("provider unavailable", refreshed.stderr)

  def test_lane_view_is_deterministic_across_fresh_processes(self):
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

      set_provider_failure(env, info="provider unavailable", dependency="provider unavailable")

      first = self.run_rwf(root, env, "lanes", "view")
      second = self.run_rwf(root, env, "lanes", "view")
      self.assertEqual(first.returncode, 0, first.stderr)
      self.assertEqual(second.returncode, 0, second.stderr)
      self.assertEqual(first.stdout, second.stdout)
      self.assertNotIn("provider unavailable", first.stderr)
      self.assertNotIn("provider unavailable", second.stderr)

  def test_lane_flag_combinations_are_accepted_by_public_grammar(self):
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

      viewed = self.run_rwf(
        root,
        env,
        "lanes",
        "view",
        "--refresh",
        "--debug",
      )
      self.assertEqual(viewed.returncode, 0, viewed.stderr)
      self.assertIn("DATA SOURCES", viewed.stdout)
      self.assertIn("DIRECT EDGES", viewed.stdout)

      listed = self.run_rwf(
        root,
        env,
        "lanes",
        "list",
        "--refresh",
        "--links",
      )
      self.assertEqual(listed.returncode, 0, listed.stderr)
      self.assertIn("https://", listed.stdout)

  def test_lane_progress_debug_and_diagnostic_records_reflect_real_provider_use(self):
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
      self.assertIn("Refreshing dependencies: #203", selected.stderr)
      self.assertIn("Refreshing dependencies: #201", selected.stderr)
      self.assertIn("Refreshing metadata: #203", selected.stderr)
      self.assertIn("Refreshing metadata: #201", selected.stderr)

      diagnostics_dir = (
        root
        / ".git"
        / "repoworkflow"
        / "diagnostics"
        / "lanes"
      )
      records = sorted(diagnostics_dir.glob("lane-invocation--*.json"))
      self.assertEqual(len(records), 1)
      first = json.loads(records[0].read_text(encoding="utf-8"))
      self.assertEqual(first["provider_calls"]["dependencies"], 2)
      self.assertEqual(first["provider_calls"]["metadata"], 2)
      self.assertEqual(first["cache_misses"]["relationships"], 2)
      self.assertEqual(first["cache_misses"]["metadata"], 2)
      self.assertTrue(first["success"])

      viewed = self.run_rwf(
        root,
        env,
        "lanes",
        "view",
        "--debug",
      )
      self.assertEqual(viewed.returncode, 0, viewed.stderr)
      self.assertNotIn("Refreshing ", viewed.stderr)
      self.assertIn("DATA SOURCES", viewed.stdout)
      self.assertIn("provider requests: 0", viewed.stdout)
      self.assertIn("metadata: cache hits=2 misses=0", viewed.stdout)
      self.assertIn("relationships: cache hits=2 misses=0", viewed.stdout)
      self.assertIn("DIRECT EDGES", viewed.stdout)
      self.assertIn("201 -> 203", viewed.stdout)

      records = sorted(
        diagnostics_dir.glob("lane-invocation--*.json"),
        key=lambda path: path.stat().st_mtime_ns,
      )
      self.assertEqual(len(records), 2)
      second = json.loads(records[-1].read_text(encoding="utf-8"))
      self.assertEqual(second["provider_calls"], {})
      self.assertEqual(second["cache_hits"]["metadata"], 2)
      self.assertEqual(second["cache_hits"]["relationships"], 2)
      self.assertEqual(second["semantic_edges"], [[201, 203]])

      refreshed = self.run_rwf(
        root,
        env,
        "lanes",
        "view",
        "--refresh",
      )
      self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
      self.assertIn("Refreshing dependencies:", refreshed.stderr)
      self.assertIn("Refreshing metadata:", refreshed.stderr)

  
  def test_diagnostic_record_survives_fresh_process_readback(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)

      selected = self.run_rwf(root, env, "lanes", "select", "203", "--json")
      self.assertEqual(selected.returncode, 0, selected.stderr)

      diagnostics_dir = (
        root
        / ".git"
        / "repoworkflow"
        / "diagnostics"
        / "lanes"
      )
      records = list(diagnostics_dir.glob("lane-invocation--*.json"))
      self.assertEqual(len(records), 1)
      record_path = records[0]

      readback = subprocess.run(
        [
          sys.executable,
          "-c",
          (
            "import json,sys;"
            "value=json.load(open(sys.argv[1],encoding='utf-8'));"
            "print(json.dumps({"
            "'schema_version':value['schema_version'],"
            "'invocation_id':value['invocation_id'],"
            "'repository_head':value['repository_head'],"
            "'command':value['command'],"
            "'success':value['success']"
            "},sort_keys=True))"
          ),
          str(record_path),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
      )
      value = json.loads(readback.stdout)
      self.assertEqual(value["schema_version"], 1)
      self.assertRegex(
        value["invocation_id"],
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
        r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
      )
      self.assertRegex(value["repository_head"], r"^[0-9a-f]{40}$")
      self.assertEqual(
        value["command"],
        ["lanes", "select", "203", "--json"],
      )
      self.assertTrue(value["success"])

  
  def test_route_render_and_diagnostics_are_stable_across_processes(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(
        base,
        {
          77: [],
          78: [77],
          99: [78],
          100: [77, 78, 99],
        },
      )

      selected = self.run_rwf(root, env, "lanes", "select", "100", "--json")
      self.assertEqual(selected.returncode, 0, selected.stderr)

      first = self.run_rwf(root, env, "lanes", "view")
      second = self.run_rwf(root, env, "lanes", "view")
      self.assertEqual(first.returncode, 0, first.stderr)
      self.assertEqual(second.returncode, 0, second.stderr)
      self.assertEqual(first.stdout, second.stdout)

      first_debug = self.run_rwf(root, env, "lanes", "view", "--debug")
      second_debug = self.run_rwf(root, env, "lanes", "view", "--debug")
      self.assertEqual(first_debug.returncode, 0, first_debug.stderr)
      self.assertEqual(second_debug.returncode, 0, second_debug.stderr)
      self.assertIn("\nROUTES\n", first_debug.stdout)
      self.assertIn("\nROUTES\n", second_debug.stdout)
      self.assertEqual(
        first_debug.stdout.split("\nROUTES\n", 1)[1],
        second_debug.stdout.split("\nROUTES\n", 1)[1],
      )
