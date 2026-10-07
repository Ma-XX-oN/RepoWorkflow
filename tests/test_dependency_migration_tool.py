from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "migrate-native-dependencies.py"


class DependencyMigrationToolTests(unittest.TestCase):
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
        "git", "remote", "add", "origin",
        "https://github.com/Ma-XX-oN/RepoWorkflow.git",
      ],
      cwd=root,
      check=True,
    )

  def manifest(self, path: Path) -> None:
    value = {
      "schema_version": 1,
      "migration_id": "repoworkflow-native-dependencies-v1",
      "repository": "Ma-XX-oN/RepoWorkflow",
      "semantics": "test direct dependency migration",
      "source_snapshot": {
        "issue_count": 3,
        "reviewed_issue_count": 3,
        "generated_from": "test fixture",
        "reviewed_through_issue": 3,
      },
      "excluded_issues": [],
      "unresolved": [],
      "issues": {
        "1": {
          "blocked_by": [],
          "provenance": ["reviewed:no-direct-edge"],
        },
        "2": {
          "blocked_by": [1],
          "provenance": ["test:direct"],
        },
        "3": {
          "blocked_by": [1, 2],
          "provenance": ["test:direct"],
        },
      },
    }
    path.write_text(json.dumps(value), encoding="utf-8")

  def fake_gh(self, base: Path, state: dict) -> dict[str, str]:
    state_path = base / "provider.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    bin_dir = base / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
      "#!/usr/bin/env python3\n"
      "import json, os, pathlib, sys\n"
      "state_path = pathlib.Path(os.environ['FAKE_GH_STATE'])\n"
      "state = json.loads(state_path.read_text())\n"
      "args = sys.argv[1:]\n"
      "def save(): state_path.write_text(json.dumps(state, sort_keys=True))\n"
      "if args[:2] == ['issue', 'view']:\n"
      "  issue = args[2]\n"
      "  if state.get('fail_read') == issue:\n"
      "    print('injected read failure', file=sys.stderr); raise SystemExit(1)\n"
      "  deps = state['deps'].get(issue, [])\n"
      "  dependants = sorted(int(number) for number, values in state['deps'].items() if int(issue) in values)\n"
      "  total = state.get('total_override', {}).get(issue, len(deps))\n"
      "  blocked_nodes = [{'number': n, 'title': f'Issue {n}', "
      "'url': f'https://example.invalid/{n}', 'state': 'OPEN'} for n in deps]\n"
      "  blocking_nodes = [{'number': n, 'title': f'Issue {n}', "
      "'url': f'https://example.invalid/{n}', 'state': 'OPEN'} for n in dependants]\n"
      "  print(json.dumps({\n"
      "    'blockedBy': {'nodes': blocked_nodes, 'totalCount': total},\n"
      "    'blocking': {'nodes': blocking_nodes, 'totalCount': len(blocking_nodes)},\n"
      "  }))\n"
      "elif args[:2] == ['issue', 'edit']:\n"
      "  issue = args[2]\n"
      "  if state.get('fail_edit') == issue:\n"
      "    print('injected edit failure', file=sys.stderr); raise SystemExit(1)\n"
      "  deps = set(state['deps'].get(issue, []))\n"
      "  if '--remove-blocked-by' in args:\n"
      "    raw = args[args.index('--remove-blocked-by') + 1]\n"
      "    deps -= {int(x) for x in raw.split(',') if x}\n"
      "  if '--add-blocked-by' in args:\n"
      "    raw = args[args.index('--add-blocked-by') + 1]\n"
      "    deps |= {int(x) for x in raw.split(',') if x}\n"
      "  if state.get('ignore_edit') != issue:\n"
      "    state['deps'][issue] = sorted(deps)\n"
      "  state['edits'] = state.get('edits', 0) + 1\n"
      "  save()\n"
      "else:\n"
      "  print('unexpected gh args: ' + repr(args), file=sys.stderr)\n"
      "  raise SystemExit(2)\n",
      encoding="utf-8",
    )
    gh.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["FAKE_GH_STATE"] = str(state_path)
    return env

  def run_tool(
    self,
    root: Path,
    manifest: Path,
    env: dict[str, str],
    *args: str,
  ):
    return subprocess.run(
      [
        sys.executable,
        str(SCRIPT),
        "--root",
        str(root),
        "--manifest",
        str(manifest),
        *args,
      ],
      cwd=root,
      env=env,
      capture_output=True,
      text=True,
    )

  def state(self, env: dict[str, str]) -> dict:
    return json.loads(Path(env["FAKE_GH_STATE"]).read_text(encoding="utf-8"))

  def setup_case(self, td: str, state: dict):
    base = Path(td)
    root = base / "repo"
    root.mkdir()
    self.make_repo(root)
    manifest = base / "manifest.json"
    self.manifest(manifest)
    env = self.fake_gh(base, state)
    return root, manifest, env

  def test_dry_run_is_read_only_and_reports_complete_diff(self):
    with tempfile.TemporaryDirectory() as td:
      root, manifest, env = self.setup_case(
        td, {"deps": {"1": [], "2": [], "3": []}, "edits": 0}
      )
      result = self.run_tool(root, manifest, env)
      self.assertEqual(result.returncode, 0, result.stderr)
      report = json.loads(result.stdout)
      self.assertEqual(report["mode"], "dry-run")
      self.assertEqual(
        report["counts"],
        {"MATCH": 1, "DESTINATION_EMPTY": 2, "CONFLICT": 0},
      )
      self.assertEqual(self.state(env)["edits"], 0)

  def test_apply_populates_empty_destinations_and_replay_is_idempotent(self):
    with tempfile.TemporaryDirectory() as td:
      root, manifest, env = self.setup_case(
        td, {"deps": {"1": [], "2": [], "3": []}, "edits": 0}
      )
      first = self.run_tool(root, manifest, env, "--apply")
      self.assertEqual(first.returncode, 0, first.stderr)
      self.assertEqual(
        self.state(env)["deps"],
        {"1": [], "2": [1], "3": [1, 2]},
      )
      edits = self.state(env)["edits"]
      second = self.run_tool(root, manifest, env, "--apply")
      self.assertEqual(second.returncode, 0, second.stderr)
      self.assertEqual(self.state(env)["edits"], edits)
      self.assertEqual(json.loads(second.stdout)["counts"]["MATCH"], 3)

  def test_conflict_fails_preflight_before_any_write(self):
    with tempfile.TemporaryDirectory() as td:
      root, manifest, env = self.setup_case(
        td,
        {"deps": {"1": [], "2": [3], "3": []}, "edits": 0},
      )
      result = self.run_tool(root, manifest, env, "--apply")
      self.assertEqual(result.returncode, 2)
      self.assertIn("has conflicts", result.stderr)
      state = self.state(env)
      self.assertEqual(state["edits"], 0)
      self.assertEqual(state["deps"]["3"], [])

  def test_reconcile_explicitly_replaces_conflicting_sets(self):
    with tempfile.TemporaryDirectory() as td:
      root, manifest, env = self.setup_case(
        td,
        {"deps": {"1": [], "2": [3], "3": [2]}, "edits": 0},
      )
      result = self.run_tool(root, manifest, env, "--reconcile")
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(
        self.state(env)["deps"],
        {"1": [], "2": [1], "3": [1, 2]},
      )

  def test_mid_run_provider_failure_reports_failure_and_never_full_success(self):
    with tempfile.TemporaryDirectory() as td:
      root, manifest, env = self.setup_case(
        td,
        {
          "deps": {"1": [], "2": [], "3": []},
          "edits": 0,
          "fail_edit": "3",
        },
      )
      result = self.run_tool(root, manifest, env, "--apply")
      self.assertEqual(result.returncode, 2)
      self.assertIn("mutation failed for #3", result.stderr)
      state = self.state(env)
      self.assertEqual(state["deps"]["2"], [1])
      self.assertEqual(state["deps"]["3"], [])

  def test_provider_readback_mismatch_fails(self):
    with tempfile.TemporaryDirectory() as td:
      root, manifest, env = self.setup_case(
        td,
        {
          "deps": {"1": [], "2": [], "3": []},
          "edits": 0,
          "ignore_edit": "3",
        },
      )
      result = self.run_tool(root, manifest, env, "--apply")
      self.assertEqual(result.returncode, 2)
      self.assertIn("mutation failed for #3", result.stderr)

  def test_truncated_provider_read_fails_before_mutation(self):
    with tempfile.TemporaryDirectory() as td:
      root, manifest, env = self.setup_case(
        td,
        {
          "deps": {"1": [], "2": [1], "3": []},
          "edits": 0,
          "total_override": {"2": 2},
        },
      )
      result = self.run_tool(root, manifest, env, "--apply")
      self.assertEqual(result.returncode, 2)
      self.assertIn("truncated", result.stderr)
      self.assertEqual(self.state(env)["edits"], 0)

  def test_provider_read_failure_prevents_all_writes(self):
    with tempfile.TemporaryDirectory() as td:
      root, manifest, env = self.setup_case(
        td,
        {
          "deps": {"1": [], "2": [], "3": []},
          "edits": 0,
          "fail_read": "2",
        },
      )
      result = self.run_tool(root, manifest, env, "--apply")
      self.assertEqual(result.returncode, 2)
      self.assertIn("cannot read native dependencies for #2", result.stderr)
      self.assertEqual(self.state(env)["edits"], 0)


if __name__ == "__main__":
  unittest.main()
