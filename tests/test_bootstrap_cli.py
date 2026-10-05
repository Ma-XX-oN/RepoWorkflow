from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from repo_workflow.public_commands import COMMANDS


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "repo_workflow.py"


def static_prefixes(node: dict, prefix: tuple[str, ...] = ()):
  for token, value in node.items():
    if not token or token.startswith("_"):
      continue
    current = (*prefix, token)
    yield current
    if isinstance(value, dict):
      yield from static_prefixes(value, current)


class BootstrapCliTests(unittest.TestCase):
  def make_repo(self, root: Path) -> None:
    subprocess.run(
      ["git", "init", "-b", "main"],
      cwd=root,
      check=True,
      capture_output=True,
      text=True,
    )

  def run_cli(self, root: Path, *args: str):
    return subprocess.run(
      [sys.executable, str(CLI), "--root", str(root), *args],
      capture_output=True,
      text=True,
    )

  def test_every_static_public_prefix_help_is_configuration_independent(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)

      prefixes = [(), *static_prefixes(COMMANDS)]
      prefixes.append(("validate", "integration"))
      for prefix in prefixes:
        with self.subTest(prefix=prefix):
          completed = self.run_cli(root, *prefix, "--help")
          self.assertEqual(completed.returncode, 0, completed.stderr)
          self.assertNotIn("repoworkflow.json", completed.stderr)
          self.assertNotIn("missing RepoWorkflow configuration", completed.stderr)

  def test_invalid_syntax_is_reported_before_missing_configuration(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)

      for args in [("frobnicate",), ("issue", "frobnicate")]:
        with self.subTest(args=args):
          completed = self.run_cli(root, *args)
          self.assertEqual(completed.returncode, 2)
          self.assertIn("unrecognised command", completed.stderr)
          self.assertNotIn("repoworkflow.json", completed.stderr)

  def test_configuration_required_command_loads_config_after_parse(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)

      completed = self.run_cli(root, "version")
      self.assertEqual(completed.returncode, 2)
      self.assertIn("missing RepoWorkflow configuration", completed.stderr)
      self.assertNotIn("unrecognised command", completed.stderr)

  def test_read_only_issue_queries_do_not_require_workflow_configuration(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)

      for args in [("issue", "list"), ("issue", "info", "297")]:
        with self.subTest(args=args):
          completed = self.run_cli(root, *args)
          self.assertEqual(completed.returncode, 2)
          self.assertIn("no GitHub remote could be discovered", completed.stderr)
          self.assertNotIn("repoworkflow.json", completed.stderr)


if __name__ == "__main__":
  unittest.main()
