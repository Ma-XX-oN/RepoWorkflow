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


def fixture_provider(arguments: list[str]) -> int:
  """Strict process-level stand-in for dependency get/replace; never runs gh."""
  state_path = Path(os.environ["FAKE_GH_STATE"])
  state = json.loads(state_path.read_text(encoding="utf-8"))
  with Path(os.environ["FAKE_PROVIDER_CALLS"]).open("a", encoding="utf-8") as log:
    log.write(json.dumps(arguments) + "\n")
  if len(arguments) < 3 or arguments[0] != "dependency":
    print("unexpected provider arguments", file=sys.stderr)
    return 2
  op, issue = arguments[1], arguments[2]
  if not issue.isdecimal() or int(issue) < 1 or issue not in state["deps"]:
    print("unexpected dependency issue", file=sys.stderr)
    return 2
  if op == "get" and len(arguments) == 3:
    if state.get("fail_read") == issue:
      print("injected read failure", file=sys.stderr)
      return 2
    deps = state["deps"][issue]
    total = state.get("total_override", {}).get(issue, len(deps))
    if total != len(deps):
      print("truncated provider dependency connection", file=sys.stderr)
      return 2
  elif op == "replace" and all(
    item.isdecimal() and int(item) > 0 for item in arguments[3:]
  ):
    if state.get("fail_edit") == issue:
      print("injected edit failure", file=sys.stderr)
      return 2
    deps = sorted({int(item) for item in arguments[3:]})
    state["edits"] = state.get("edits", 0) + 1
    if state.get("ignore_edit") != issue:
      state["deps"][issue] = deps
    state_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    deps = state["deps"][issue]
  else:
    print("unexpected provider arguments", file=sys.stderr)
    return 2
  print(json.dumps({
    "schema_version": 1, "issue": int(issue), "dependencies": deps,
  }))
  return 0


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
    """Inject a Python dependency provider through the product's command seam."""
    state_path = base / "provider.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    calls = base / "provider-calls.jsonl"
    calls.write_text("", encoding="utf-8")
    env = dict(os.environ)
    env.pop("GH_TOKEN", None)
    env.pop("GITHUB_TOKEN", None)
    env["FAKE_GH_STATE"] = str(state_path)
    env["FAKE_PROVIDER_CALLS"] = str(calls)
    config = {
      "schema": 1,
      "versionCommand": [sys.executable, "-c", "print('1.0.0')"],
      "repository": {
        "integrationBranch": "main", "authoritativeRemote": "origin",
      },
      "environments": [{
        "id": "fixture", "platform": "any",
        "validationCommand": [sys.executable, "-c", "print('ok')"],
      }],
      "dependencyCommand": [
        sys.executable, str(Path(__file__).resolve()), "--fixture-provider",
      ],
    }
    path = base / "repo" / ".ci" / "repoworkflow.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config), encoding="utf-8")
    return env

  def verify_provider(self, root: Path, env: dict[str, str]) -> None:
    configured = json.loads(
      (root / ".ci" / "repoworkflow.json").read_text(encoding="utf-8")
    )["dependencyCommand"]
    expected = [
      sys.executable, str(Path(__file__).resolve()), "--fixture-provider",
    ]
    if configured != expected or "GH_TOKEN" in env or "GITHUB_TOKEN" in env:
      raise RuntimeError("nonhermetic dependencyCommand: refusing real gh")

  def run_tool(
    self,
    root: Path,
    manifest: Path,
    env: dict[str, str],
    *args: str,
  ):
    self.verify_provider(root, env)
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

  def test_provider_boundary_never_resolves_real_gh(self):
    with tempfile.TemporaryDirectory() as td:
      root, manifest, env = self.setup_case(
        td, {"deps": {"1": [], "2": [], "3": []}, "edits": 0}
      )
      self.assertNotIn("GH_TOKEN", env)
      self.assertNotIn("GITHUB_TOKEN", env)
      result = self.run_tool(root, manifest, env)
      self.assertEqual(result.returncode, 0, result.stderr)
      calls = [
        json.loads(line) for line in
        Path(env["FAKE_PROVIDER_CALLS"]).read_text(encoding="utf-8").splitlines()
      ]
      self.assertEqual(calls, [
        ["dependency", "get", "1"],
        ["dependency", "get", "2"],
        ["dependency", "get", "3"],
      ])
      config = root / ".ci" / "repoworkflow.json"
      data = json.loads(config.read_text(encoding="utf-8"))
      data["dependencyCommand"] = ["gh", "issue", "view"]
      config.write_text(json.dumps(data), encoding="utf-8")
      with self.assertRaisesRegex(RuntimeError, "nonhermetic dependencyCommand"):
        self.run_tool(root, manifest, env)
      self.assertEqual(len(calls), len(
        Path(env["FAKE_PROVIDER_CALLS"]).read_text(
          encoding="utf-8"
        ).splitlines()
      ))

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
  if len(sys.argv) > 1 and sys.argv[1] == "--fixture-provider":
    raise SystemExit(fixture_provider(sys.argv[2:]))
  unittest.main()
