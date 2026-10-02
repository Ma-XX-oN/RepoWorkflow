import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from repo_workflow.config import load_config
from repo_workflow.prelim import start_prelim
from repo_workflow.workflow_state import save_local_state
from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "repo_workflow.py"


class WorkflowCliTests(unittest.TestCase):
  def run_cli(self, root: Path, *args: str):
    return subprocess.run(
      [sys.executable, str(CLI), "--root", str(root), *args],
      capture_output=True,
      text=True,
    )

  def test_human_and_json_what_next_report_same_transitions(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      save_local_state(root, fx.head(), regression="PASS", integrationResult=None)

      machine = self.run_cli(root, "what-next", "--json")
      human = self.run_cli(root, "what-next")
      self.assertEqual(machine.returncode, 0, machine.stderr)
      self.assertEqual(human.returncode, 0, human.stderr)
      value = json.loads(machine.stdout)
      human_transitions = {
        line.strip()
        for line in human.stdout.splitlines()[1:]
        if line.startswith("  ") and not line.startswith("  (")
      }
      self.assertTrue(set(value["transitions"]).issubset(human_transitions))

  def test_what_next_is_deterministic_for_unchanged_state(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      save_local_state(root, fx.head(), regression="PASS", integrationResult=None)

      first = self.run_cli(root, "what-next", "--json")
      second = self.run_cli(root, "what-next", "--json")

      self.assertEqual(first.returncode, 0, first.stderr)
      self.assertEqual(second.returncode, 0, second.stderr)
      self.assertEqual(first.stdout, second.stdout)

  def test_what_next_fails_closed_without_authorization(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      save_local_state(
        root,
        fx.head(),
        regression="PASS",
        integrationResult="succeeded",
      )
      completed = self.run_cli(root, "what-next", "--json")
      value = json.loads(completed.stdout)
      self.assertNotIn("integrate", value["transitions"])
      self.assertTrue(any("authorization absent" in block for block in value["blocks"]))

  def test_version_query_and_forwarding_use_repository_adapter(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      queried = self.run_cli(root, "version")
      self.assertEqual(queried.returncode, 0, queried.stderr)
      self.assertEqual(queried.stdout.strip(), fx.version)

      advanced = self.run_cli(root, "version", "integrate", "increment", "patch")
      self.assertEqual(advanced.returncode, 2)
      self.assertIn("GUID-qualified preliminary integration branch", advanced.stderr)

  def test_release_intent_succeeds_on_guid_prelim_from_task_base(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)
      started = start_prelim(root, load_config(root))
      self.assertTrue(started.branch.startswith("prelim-main-"))

      completed = self.run_cli(
        root,
        "version",
        "integrate",
        "increment",
        "patch",
      )

      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertEqual(completed.stdout.strip(), "1.0.1")
      self.assertEqual((root / "VERSION").read_text().strip(), "1.0.1")

  def test_version_query_supports_json(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)

      completed = self.run_cli(root, "version", "--json")

      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertEqual(json.loads(completed.stdout), {"version": fx.version})

  def test_hidden_completion_command_uses_state_machine(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      config_path = root / ".ci" / "repoworkflow.json"
      config = json.loads(config_path.read_text(encoding="utf-8"))
      config["manualIntegrationRequired"] = True
      config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
      fx.commit("require manual integration")
      save_local_state(
        root,
        fx.head(),
        regression="PASS",
        automaticIntegration="PASS",
      )
      completed = self.run_cli(root, "complete", "validate", "integration", "")
      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertEqual(completed.stdout.splitlines(), ["failed", "succeeded"])


if __name__ == "__main__":
  unittest.main()
