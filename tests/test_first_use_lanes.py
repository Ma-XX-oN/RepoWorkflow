from __future__ import annotations

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
    titles = {
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
      "if args[:2] == ['issue', 'view'] and 'blockedBy' in args:\n"
      "  number = int(args[2])\n"
      "  with open(os.environ['RWF_TEST_CALLS'], 'a', encoding='utf-8') as log:\n"
      "    log.write(json.dumps({'kind': 'dependency', 'issue': number}) + '\\n')\n"
      "  state = json.load(open(os.environ['RWF_TEST_DEPS'], encoding='utf-8'))\n"
      "  deps = state[str(number)]\n"
      "  nodes = [{'number': n, 'title': f'Issue {n}', "
      "'url': f'https://github.com/Ma-XX-oN/RepoWorkflow/issues/{n}', "
      "'state': 'OPEN'} for n in deps]\n"
      "  print(json.dumps({'blockedBy': "
      "{'nodes': nodes, 'totalCount': len(nodes)}}))\n"
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

      graph = root / ".repoworkflow" / "state" / "relationships" / "graph.json"
      self.assertTrue(graph.is_file())
      graph_value = json.loads(graph.read_text(encoding="utf-8"))
      self.assertEqual(graph_value["revision"], 0)
      self.assertEqual(
        graph_value["value"]["issues"]["203"]["depends_on"],
        ["201"],
      )

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
      self.assertIn("A.201", viewed.stdout)
      self.assertIn("A.203", viewed.stdout)
      self.assertIn("B.206", viewed.stdout)
      self.assertIn("─", viewed.stdout)
      self.assertNotIn("Leaf 201", viewed.stdout)
      self.assertNotIn("Root 203", viewed.stdout)

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
      self.assertIn("A.201", selected.stdout)
      self.assertIn("A.203", selected.stdout)

      listed = self.run_rwf(root, env, "lanes", "list")
      self.assertEqual(listed.returncode, 0, listed.stderr)
      self.assertIn("#201  Leaf 201", listed.stdout)
      self.assertIn("#203  Root 203", listed.stdout)
      self.assertIn("#206  Root 206", listed.stdout)
      self.assertNotIn("─", listed.stdout)

      viewed = self.run_rwf(root, env, "lanes", "view")
      self.assertEqual(viewed.returncode, 0, viewed.stderr)
      self.assertIn("A.201", viewed.stdout)
      self.assertIn("A.203", viewed.stdout)
      self.assertNotIn("Leaf 201", viewed.stdout)
      self.assertNotIn("Root 203", viewed.stdout)

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
      first = self.run_rwf(root, env, "lanes", "list")
      self.assertIn("#203  Root 203", first.stdout)

      metadata_path = Path(env["RWF_TEST_META"])
      metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
      metadata["203"]["title"] = "Updated Root 203"
      metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

      cached = self.run_rwf(root, env, "lanes", "list")
      self.assertIn("#203  Root 203", cached.stdout)
      self.assertNotIn("Updated Root 203", cached.stdout)

      refreshed = self.run_rwf(
        root,
        env,
        "lanes",
        "list",
        "--refresh",
      )
      self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
      self.assertIn("#203  Updated Root 203", refreshed.stdout)

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
      self.assertIn("A.201", viewed.stdout)
      self.assertIn("A.203", viewed.stdout)

      refreshed = self.run_rwf(
        root,
        env,
        "lanes",
        "view",
        "--refresh",
      )
      self.assertEqual(refreshed.returncode, 2)
      self.assertIn("provider unavailable", refreshed.stderr)

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

      graph = root / ".repoworkflow" / "state" / "relationships" / "graph.json"
      graph_value = json.loads(graph.read_text(encoding="utf-8"))
      self.assertEqual(graph_value["revision"], 2)
      self.assertEqual(
        sorted(graph_value["value"]["issues"], key=int),
        ["201", "203", "205", "206", "208", "217", "218"],
      )
      self.assertEqual(
        graph_value["value"]["issues"]["203"]["depends_on"],
        ["201"],
      )
      self.assertEqual(
        graph_value["value"]["issues"]["205"]["depends_on"],
        ["208"],
      )
      self.assertEqual(
        graph_value["value"]["issues"]["218"]["depends_on"],
        ["217"],
      )

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
        [203, 201, 203, 201],
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
        [203, 201],
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
      graph_path = (
        root
        / ".repoworkflow"
        / "state"
        / "relationships"
        / "graph.json"
      )
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

      graph = root / ".repoworkflow" / "state" / "relationships" / "graph.json"
      value = json.loads(graph.read_text(encoding="utf-8"))
      self.assertEqual(value["value"]["issues"]["203"]["depends_on"], ["201"])
      self.assertIn("201", value["value"]["issues"])

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
        json.dumps({"203": [206], "206": []}),
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

      graph = root / ".repoworkflow" / "state" / "relationships" / "graph.json"
      value = json.loads(graph.read_text(encoding="utf-8"))
      self.assertEqual(value["value"]["issues"]["203"]["depends_on"], ["201"])
      self.assertNotIn("206", value["value"]["issues"])

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
        (
          root
          / ".repoworkflow"
          / "state"
          / "relationships"
          / "graph.json"
        ).exists()
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
