from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RWF = ROOT / "rwf"


class FirstUseLanesTests(unittest.TestCase):
  def make_repo(self, root: Path) -> None:
    subprocess.run(
      ["git", "init", "-b", "main"],
      cwd=root,
      check=True,
      capture_output=True,
      text=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    subprocess.run(
      ["git", "config", "user.email", "test@example.invalid"],
      cwd=root,
      check=True,
    )
    subprocess.run(
      ["git", "commit", "--allow-empty", "-m", "initial"],
      cwd=root,
      check=True,
      capture_output=True,
      text=True,
    )
    subprocess.run(
      [
        "git",
        "remote",
        "add",
        "origin",
        "https://github.com/Ma-XX-oN/RepoWorkflow.git",
      ],
      cwd=root,
      check=True,
    )

  def fake_github(
    self,
    base: Path,
    dependencies: dict[int, list[int]] | None = None,
    titles: dict[int, str] | None = None,
  ) -> dict[str, str]:
    if dependencies is None:
      dependencies = {
        206: [],
        203: [201],
        201: [],
        205: [208],
        208: [],
        218: [217],
        217: [],
        187: [],
        189: [],
      }
    dependency_state = base / "dependencies.json"
    metadata_state = base / "metadata.json"
    call_log = base / "dependency-calls.jsonl"
    call_log.write_text("", encoding="utf-8")
    all_numbers = sorted({
      number
      for number, deps in dependencies.items()
      for number in (number, *deps)
    })
    default_titles = {
      206: "Root 206",
      203: "Root 203",
      201: "Leaf 201",
      205: "Root 205",
      208: "Leaf 208",
      218: "Root 218",
      217: "Leaf 217",
      187: "Leaf A",
      189: "Leaf B",
    }
    titles = default_titles if titles is None else {**default_titles, **titles}
    metadata_state.write_text(
      json.dumps({
        str(number): {
          "title": titles.get(number, f"Issue {number}"),
          "state": "OPEN",
        }
        for number in all_numbers
      }),
      encoding="utf-8",
    )
    dependency_state.write_text(
      json.dumps({str(key): value for key, value in dependencies.items()}),
      encoding="utf-8",
    )
    bin_dir = base / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
      "#!/usr/bin/env python3\n"
      "import json, os, sys\n"
      "args = sys.argv[1:]\n"
      "if args[:2] == ['issue', 'view'] and any('blockedBy' in arg for arg in args):\n"
      "  number = int(args[2])\n"
      "  with open(os.environ['RWF_TEST_CALLS'], 'a', encoding='utf-8') as log:\n"
      "    log.write(json.dumps({'kind': 'dependency', 'issue': number}) + '\\n')\n"
      "  state = json.load(open(os.environ['RWF_TEST_DEPS'], encoding='utf-8'))\n"
      "  deps = state[str(number)]\n"
      "  dependants = sorted(int(issue) for issue, values in state.items() if number in values)\n"
      "  def connection(values):\n"
      "    nodes = [{'number': n, 'title': f'Issue {n}', "
      "'url': f'https://github.com/Ma-XX-oN/RepoWorkflow/issues/{n}', "
      "'state': 'OPEN'} for n in values]\n"
      "    return {'nodes': nodes, 'totalCount': len(nodes)}\n"
      "  print(json.dumps({\n"
      "    'blockedBy': connection(deps),\n"
      "    'blocking': connection(dependants),\n"
      "  }))\n"
      "elif args[:2] == ['issue', 'view']:\n"
      "  number = int(args[2])\n"
      "  state = json.load(open(os.environ['RWF_TEST_META'], encoding='utf-8'))\n"
      "  item = state[str(number)]\n"
      "  print(json.dumps({'number': number, 'title': item['title'], "
      "'state': item['state'], 'url': "
      "f'https://github.com/Ma-XX-oN/RepoWorkflow/issues/{number}'}))\n"
      "else:\n"
      "  print('unexpected gh arguments: ' + repr(args), file=sys.stderr)\n"
      "  raise SystemExit(2)\n",
      encoding="utf-8",
    )
    gh.chmod(0o755)
    env = dict(os.environ)
    env.pop("RWF_WRITER_ID", None)
    env.pop("RWF_SESSION_ID", None)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["RWF_TEST_DEPS"] = str(dependency_state)
    env["RWF_TEST_META"] = str(metadata_state)
    env["RWF_TEST_CALLS"] = str(call_log)
    return env

  def ticket_rows(self, root: Path) -> dict[str, dict[str, str]]:
    path = root / ".repoworkflow" / "tickets.csv"
    with path.open(newline="", encoding="utf-8") as handle:
      return {
        row["issue"]: row
        for row in csv.DictReader(handle)
      }

  def dependency_calls(self, env: dict[str, str]) -> list[int]:
    path = Path(env["RWF_TEST_CALLS"])
    return [
      json.loads(line)["issue"]
      for line in path.read_text(encoding="utf-8").splitlines()
      if line
    ]

  def certify_migration(self, root: Path) -> None:
    source = (
      ROOT
      / ".repoworkflow"
      / "migrations"
      / "native-dependencies-v1.json"
    )
    target = (
      root
      / ".repoworkflow"
      / "migrations"
      / "native-dependencies-v1.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    certification = {
      "schema_version": 1,
      "migration_id": "repoworkflow-native-dependencies-v1",
      "repository": "Ma-XX-oN/RepoWorkflow",
      "manifest_sha256": digest,
      "provider_readback_sha256": "0" * 64,
    }
    target.with_name("native-dependencies-v1.certified.json").write_text(
      json.dumps(certification),
      encoding="utf-8",
    )

  def run_rwf(self, root: Path, env: dict[str, str], *words: str):
    return subprocess.run(
      [str(RWF), "--root", str(root), *words],
      cwd=root,
      env=env,
      capture_output=True,
      text=True,
    )

  def test_fresh_checkout_selects_and_renders_ticket_dependency_closure(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)

      selected = self.run_rwf(root, env, "lanes", "select", "203", "206", "--json")
      self.assertEqual(selected.returncode, 0, selected.stderr)
      value = json.loads(selected.stdout)
      self.assertEqual(value["roots"], ["203", "206"])
      self.assertEqual(value["closure"], ["201", "203", "206"])

      tickets = root / ".repoworkflow" / "tickets.csv"
      self.assertTrue(tickets.is_file())
      rows = self.ticket_rows(root)
      self.assertEqual(rows["203"]["dependencies"], "201")
      self.assertEqual(rows["203"]["title"], "Root 203")

      common = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
      ).stdout.strip()
      writer = (root / common / "repoworkflow" / "runtime-writer-id").resolve()
      self.assertTrue(writer.is_file())
      self.assertTrue(writer.read_text(encoding="utf-8").startswith("local-"))

      listed = self.run_rwf(root, env, "lanes", "list")
      self.assertEqual(listed.returncode, 0, listed.stderr)
      self.assertIn("Lane A", listed.stdout)
      self.assertIn("#201  Leaf 201", listed.stdout)
      self.assertIn("#203  Root 203", listed.stdout)
      self.assertIn("Lane B", listed.stdout)
      self.assertIn("#206  Root 206", listed.stdout)
      self.assertNotIn("─", listed.stdout)

      viewed = self.run_rwf(root, env, "lanes", "view")
      self.assertEqual(viewed.returncode, 0, viewed.stderr)
      self.assertIn("A201", viewed.stdout)
      self.assertIn("A203", viewed.stdout)
      self.assertIn("B206", viewed.stdout)
      self.assertIn("─", viewed.stdout)
      self.assertNotIn("Leaf 201", viewed.stdout)
      self.assertNotIn("Root 203", viewed.stdout)

  def test_leaf_focus_discovers_complete_component_from_provider(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base, {
        435: [439],
        436: [],
        437: [436],
        438: [436],
        439: [437, 438],
      })

      selected = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "436",
        "--json",
      )
      self.assertEqual(selected.returncode, 0, selected.stderr)
      value = json.loads(selected.stdout)
      self.assertEqual(value["roots"], ["436"])
      self.assertEqual(value["closure"], ["435", "436", "437", "438", "439"])
      self.assertEqual(set(self.dependency_calls(env)), {
        435, 436, 437, 438, 439
      })

      rendered = self.run_rwf(root, env, "lanes", "select", "436")
      self.assertEqual(rendered.returncode, 0, rendered.stderr)
      self.assertIn("*A436", rendered.stdout)
      self.assertEqual(rendered.stdout.count("*"), 1)

  def test_group_boundary_stops_provider_component_until_followed(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      dependencies = {
        1: [],
        2: [1],
        3: [2],
        4: [3],
      }
      env = self.fake_github(
        base,
        dependencies,
        titles={
          1: "Issue 1",
          2: "Feature: Boundary",
          3: "Issue 3",
          4: "Issue 4",
        },
      )

      stopped = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "1",
        "--json",
      )
      self.assertEqual(stopped.returncode, 0, stopped.stderr)
      self.assertEqual(json.loads(stopped.stdout)["closure"], ["1", "2"])
      self.assertEqual(set(self.dependency_calls(env)), {1, 2})

      Path(env["RWF_TEST_CALLS"]).write_text("", encoding="utf-8")
      followed = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "1",
        "--follow",
        "feature",
        "--refresh",
        "--json",
      )
      self.assertEqual(followed.returncode, 0, followed.stderr)
      self.assertEqual(
        json.loads(followed.stdout)["closure"],
        ["1", "2", "3", "4"],
      )
      self.assertEqual(set(self.dependency_calls(env)), {1, 2, 3, 4})

  def test_show_children_fetches_one_hop_without_recursive_traversal(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(
        base,
        {
          1: [],
          2: [1],
          3: [2],
          4: [3],
        },
        titles={
          1: "Issue 1",
          2: "Feature: Boundary",
          3: "Issue 3",
          4: "Issue 4",
        },
      )

      selected = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "1",
        "--show-children",
        "feature",
        "--json",
      )
      self.assertEqual(selected.returncode, 0, selected.stderr)
      self.assertEqual(
        json.loads(selected.stdout)["closure"],
        ["1", "2", "3"],
      )
      self.assertEqual(set(self.dependency_calls(env)), {1, 2, 3})

      Path(env["RWF_TEST_CALLS"]).write_text("", encoding="utf-8")
      refreshed = self.run_rwf(
        root,
        env,
        "lanes",
        "view",
        "--refresh",
      )
      self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
      self.assertNotIn(4, self.dependency_calls(env))

      selection_path = (
        root / ".git/repoworkflow/lane-selection/selection.json"
      )
      record = json.loads(selection_path.read_text(encoding="utf-8"))
      self.assertTrue(
        record["value"]["show_children"]["feature"],
      )

  def test_show_children_support_fetch_does_not_expand_projection(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(
        base,
        {
          1: [],
          2: [1],
          3: [2],
          4: [3],
        },
        titles={
          1: "Issue 1",
          2: "Issue 2",
          3: "Feature: Boundary",
          4: "Issue 4",
        },
      )

      selected = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "4",
        "--show-children",
        "feature",
        "--json",
      )
      self.assertEqual(selected.returncode, 0, selected.stderr)
      self.assertEqual(
        json.loads(selected.stdout)["closure"],
        ["2", "3", "4"],
      )
      self.assertNotIn("1", json.loads(selected.stdout)["closure"])
      self.assertEqual(set(self.dependency_calls(env)), {1, 2, 3, 4})

  def test_refresh_preserves_consumed_follow_budget(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(
        base,
        {
          1: [],
          2: [1],
          3: [2],
          4: [3],
          5: [4],
        },
        titles={
          1: "Issue 1",
          2: "Feature: First",
          3: "Issue 3",
          4: "Feature: Second",
          5: "Issue 5",
        },
      )

      selected = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "1",
        "--follow",
        "feature",
        "--json",
      )
      self.assertEqual(selected.returncode, 0, selected.stderr)
      self.assertEqual(
        json.loads(selected.stdout)["closure"],
        ["1", "2", "3", "4"],
      )

      Path(env["RWF_TEST_CALLS"]).write_text("", encoding="utf-8")
      refreshed = self.run_rwf(
        root,
        env,
        "lanes",
        "view",
        "--refresh",
      )
      self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
      self.assertNotIn(5, self.dependency_calls(env))

      selection_path = (
        root / ".git/repoworkflow/lane-selection/selection.json"
      )
      record = json.loads(selection_path.read_text(encoding="utf-8"))
      self.assertEqual(
        record["value"]["closure"],
        ["1", "2", "3", "4"],
      )
      self.assertEqual(record["value"]["follow"]["feature"], 1)

  def test_human_select_renders_graph_and_list_uses_same_selection(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)

      selected = self.run_rwf(root, env, "lanes", "select", "203", "206")
      self.assertEqual(selected.returncode, 0, selected.stderr)
      self.assertNotIn('"schema_version"', selected.stdout)
      self.assertIn("─", selected.stdout)
      self.assertIn("*", selected.stdout)
      self.assertIn("A201", selected.stdout)
      self.assertIn("A203", selected.stdout)

      listed = self.run_rwf(root, env, "lanes", "list")
      self.assertEqual(listed.returncode, 0, listed.stderr)
      self.assertIn("#201  Leaf 201", listed.stdout)
      self.assertIn("#203  Root 203", listed.stdout)
      self.assertIn("#206  Root 206", listed.stdout)
      self.assertNotIn("─", listed.stdout)

      viewed = self.run_rwf(root, env, "lanes", "view")
      self.assertEqual(viewed.returncode, 0, viewed.stderr)
      self.assertIn("A201", viewed.stdout)
      self.assertIn("A203", viewed.stdout)
      self.assertNotIn("Leaf 201", viewed.stdout)
      self.assertNotIn("Root 203", viewed.stdout)

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

      gh = Path(env["PATH"].split(os.pathsep)[0]) / "gh"
      gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "if any('blockedBy' in arg for arg in args):\n"
        "  print('dependency provider must not be used', file=sys.stderr)\n"
        "  raise SystemExit(96)\n"
        "if args[:2] == ['issue', 'view']:\n"
        "  number = int(args[2])\n"
        "  state = json.load(open(os.environ['RWF_TEST_META'], encoding='utf-8'))\n"
        "  item = state[str(number)]\n"
        "  print(json.dumps({'number': number, 'title': item['title'], "
        "'state': item['state'], 'url': "
        "f'https://github.com/Ma-XX-oN/RepoWorkflow/issues/{number}'}))\n"
        "else:\n"
        "  raise SystemExit(97)\n",
        encoding="utf-8",
      )
      gh.chmod(0o755)

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

      gh = Path(env["PATH"].split(os.pathsep)[0]) / "gh"
      gh.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "args = sys.argv[1:]\n"
        "if any('blockedBy' in arg for arg in args):\n"
        "  print('dependency provider must not be used', file=sys.stderr)\n"
        "  raise SystemExit(96)\n"
        "print('metadata unavailable', file=sys.stderr)\n"
        "raise SystemExit(98)\n",
        encoding="utf-8",
      )
      gh.chmod(0o755)

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

      gh = Path(env["PATH"].split(os.pathsep)[0]) / "gh"
      gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "if args[:2] != ['issue', 'view'] or any('blockedBy' in arg for arg in args):\n"
        "  print('unexpected gh arguments: ' + repr(args), file=sys.stderr)\n"
        "  raise SystemExit(2)\n"
        "number = int(args[2])\n"
        "titles = {201: 'Leaf 201 refreshed', 203: 'Root 203 refreshed'}\n"
        "print(json.dumps({\n"
        "  'number': number,\n"
        "  'title': titles[number],\n"
        "  'state': 'OPEN',\n"
        "  'url': f'https://github.com/Ma-XX-oN/RepoWorkflow/issues/{number}',\n"
        "}))\n",
        encoding="utf-8",
      )
      gh.chmod(0o755)

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

      gh = Path(env["PATH"].split(os.pathsep)[0]) / "gh"
      gh.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('provider unavailable', file=sys.stderr)\n"
        "raise SystemExit(93)\n",
        encoding="utf-8",
      )
      gh.chmod(0o755)

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

      gh = Path(env["PATH"].split(os.pathsep)[0]) / "gh"
      gh.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('provider unavailable', file=sys.stderr)\n"
        "raise SystemExit(93)\n",
        encoding="utf-8",
      )
      gh.chmod(0o755)

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

      gh = Path(env["PATH"].split(os.pathsep)[0]) / "gh"
      gh.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('provider unavailable', file=sys.stderr)\n"
        "raise SystemExit(94)\n",
        encoding="utf-8",
      )
      gh.chmod(0o755)

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

      gh = Path(env["PATH"].split(os.pathsep)[0]) / "gh"
      gh.write_text(
        "#!/usr/bin/env python3\n"
        "raise SystemExit(91)\n",
        encoding="utf-8",
      )
      gh.chmod(0o755)

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

      gh = Path(env["PATH"].split(os.pathsep)[0]) / "gh"
      gh.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('provider unavailable', file=sys.stderr)\n"
        "raise SystemExit(92)\n",
        encoding="utf-8",
      )
      gh.chmod(0o755)

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
        "native ticket dependency migration is not certified",
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


if __name__ == "__main__":
  unittest.main()
