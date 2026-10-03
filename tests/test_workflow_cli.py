import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

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
        line.removeprefix("  → ")
        for line in human.stdout.splitlines()
        if line.startswith("  → ")
      }
      self.assertEqual(set(value["transitions"]), human_transitions)

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
      self.assertEqual(completed.returncode, 0, completed.stderr)
      value = json.loads(completed.stdout)
      self.assertNotIn("integrate", value["transitions"])
      self.assertTrue(any("authorization absent" in block for block in value["blocks"]))

  def test_help_matches_double_tab_projection_at_dynamic_prefix(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      save_local_state(root, fx.head(), regression="PASS", integrationResult=None)

      help_result = self.run_cli(root, "validate", "integration", "--help")
      detailed = self.run_cli(
        root,
        "complete",
        "--describe",
        "--",
        "validate",
        "integration",
        "",
      )
      self.assertEqual(help_result.returncode, 0, help_result.stderr)
      self.assertEqual(detailed.returncode, 0, detailed.stderr)
      self.assertEqual(help_result.stdout, detailed.stdout)

  def test_help_matches_double_tab_projection_at_executable_prefix(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)

      help_result = self.run_cli(root, "what-next", "--help")
      detailed = self.run_cli(
        root,
        "complete",
        "--describe",
        "--",
        "what-next",
        "",
      )
      self.assertEqual(help_result.returncode, 0, help_result.stderr)
      self.assertEqual(detailed.returncode, 0, detailed.stderr)
      self.assertEqual(help_result.stdout, detailed.stdout)
      self.assertIn("<last-terminal>", help_result.stdout)
      self.assertIn("--json", help_result.stdout)

  def test_root_help_matches_root_double_tab_projection(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)

      help_result = self.run_cli(root, "--help")
      detailed = self.run_cli(root, "complete", "--describe", "--", "")
      self.assertEqual(help_result.returncode, 0, help_result.stderr)
      self.assertEqual(detailed.returncode, 0, detailed.stderr)
      self.assertEqual(help_result.stdout, detailed.stdout)

  def test_version_query_and_json_use_repository_adapter(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)

      queried = self.run_cli(root, "version")
      self.assertEqual(queried.returncode, 0, queried.stderr)
      self.assertEqual(queried.stdout.strip(), fx.version)

      machine = self.run_cli(root, "version", "--json")
      self.assertEqual(machine.returncode, 0, machine.stderr)
      self.assertEqual(json.loads(machine.stdout), {"version": fx.version})

  def test_version_task_issue_forwards_semantic_transition(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)
      (root / "VERSION").write_text("1.2.3\n")
      completed = self.run_cli(root, "version", "task", "issue", "27")
      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertEqual(completed.stdout.strip(), "1.2.3-issue.27.0.1")

  def test_version_integration_and_major_forwarding(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)
      (root / "VERSION").write_text("1.2.3\n")

      patch = self.run_cli(root, "version", "integrate", "increment", "patch")
      self.assertEqual(patch.returncode, 0, patch.stderr)
      self.assertEqual(patch.stdout.strip(), "1.2.4")

      (root / "VERSION").write_text("1.2.3\n")
      minor = self.run_cli(root, "version", "integrate", "increment", "minor")
      self.assertEqual(minor.returncode, 0, minor.stderr)
      self.assertEqual(minor.stdout.strip(), "1.3.0")

      (root / "VERSION").write_text("1.2.3\n")
      major = self.run_cli(root, "version", "release-major")
      self.assertEqual(major.returncode, 0, major.stderr)
      self.assertEqual(major.stdout.strip(), "2.0.0")

  def test_aliases_execute_same_public_cli(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      for alias in ("repo-workflow", "rwf"):
        completed = subprocess.run(
          [str(ROOT / alias), "--root", str(root), "version"],
          capture_output=True,
          text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), fx.version)

  def test_unknown_command_uses_shared_diagnostic(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)
      completed = self.run_cli(root, "foo")
      self.assertEqual(completed.returncode, 2)
      self.assertEqual(
        completed.stderr,
        "RepoWorkflow error: unrecognised command.\n"
        "  foo\n"
        "  ^^^\n"
        "\n"
        "Legal transitions:\n"
        "  regression required\n"
        "  → validate regression\n",
      )

  def test_manually_typed_state_invalid_command_uses_shared_diagnostic(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)
      completed = self.run_cli(root, "validate", "integration", "succeeded")
      self.assertEqual(completed.returncode, 2)
      self.assertEqual(
        completed.stderr,
        "RepoWorkflow error: transition is not legal in the current state:\n"
        "  validate integration succeeded\n"
        "           ^^^^^^^^^^^\n"
        "\n"
        "Legal transitions:\n"
        "  regression required\n"
        "  → validate regression\n",
      )
      self.assertEqual((root / "VERSION").read_text().strip(), "1.0.0-issue.1.0.1")

  def test_hidden_completion_reports_state_miss_without_mutation(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)
      completed = self.run_cli(root, "complete", "validate", "integration", "s")
      self.assertEqual(completed.returncode, 2)
      self.assertEqual(completed.stdout, "")
      self.assertEqual(
        completed.stderr,
        "RepoWorkflow error: transition is not legal in the current state:\n"
        "  validate integration s\n"
        "           ^^^^^^^^^^^\n"
        "\n"
        "Legal transitions:\n"
        "  regression required\n"
        "  → validate regression\n",
      )
      self.assertEqual((root / "VERSION").read_text().strip(), "1.0.0-issue.1.0.1")

  def test_hidden_completion_projects_state_machine(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      save_local_state(root, fx.head(), regression="PASS", integrationResult=None)
      completed = self.run_cli(root, "complete", "validate", "integration", "")
      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertEqual(completed.stdout.splitlines(), ["failed", "succeeded"])


if __name__ == "__main__":
  unittest.main()
