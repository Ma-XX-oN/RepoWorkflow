from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

from repo_workflow.public_commands import COMMANDS
from repo_workflow.command_grammar import (
  CommandGrammarError, Context, parse_tokens,
)


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
    subprocess.run(
      ["git", "config", "user.name", "Test"],
      cwd=root,
      check=True,
    )
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

  def run_cli(self, root: Path, *args: str, env=None):
    return subprocess.run(
      [sys.executable, str(CLI), "--root", str(root), *args],
      capture_output=True,
      text=True,
      env=env,
    )

  def test_every_static_public_prefix_help_is_configuration_independent(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)

      prefixes = [(), *static_prefixes(COMMANDS)]
      prefixes.append(("test", "integration"))
      for prefix in prefixes:
        with self.subTest(prefix=prefix):
          completed = self.run_cli(root, *prefix, "--help")
          self.assertEqual(completed.returncode, 0, completed.stderr)
          self.assertNotIn("repoworkflow.json", completed.stderr)
          self.assertNotIn("missing RepoWorkflow configuration", completed.stderr)

  def test_root_help_describes_every_public_command(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)
      completed = self.run_cli(root, "--help")
      self.assertEqual(completed.returncode, 0, completed.stderr)
      rows = {
        parts[0]: parts[1]
        for line in completed.stdout.splitlines()
        if len(parts := line.split(maxsplit=1)) == 2
      }
      for command in COMMANDS:
        with self.subTest(command=command):
          self.assertIn(command, rows)
          self.assertTrue(rows[command].strip())

  def test_every_static_command_and_option_has_help(self):
    """All authored command descriptions must survive future grammar edits."""
    def walk(node, prefix=()):
      for token, entry in node.items():
        if not token or token.startswith("_"):
          continue
        current = (*prefix, token)
        if isinstance(entry, dict):
          description = entry.get("_description", entry.get(""))
          self.assertIsInstance(description, str, current)
          self.assertTrue(description.strip(), current)
          yield current, entry
          yield from walk(entry, current)
        elif isinstance(entry, str):
          self.assertTrue(entry.strip(), current)

    list(walk(COMMANDS))
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)
      for prefix in ((), *static_prefixes(COMMANDS)):
        with self.subTest(prefix=prefix):
          completed = self.run_cli(root, *prefix, "--help")
          self.assertEqual(completed.returncode, 0, completed.stderr)
          children = [
            (token, entry)
            for token, entry in self._static_help_children(prefix)
          ]
          displayed = {
            parts[0]: parts[1]
            for line in completed.stdout.splitlines()
            if len(parts := line.split(maxsplit=1)) == 2
          }
          for token, entry in children:
            with self.subTest(prefix=prefix, token=token):
              expected = (
                entry if isinstance(entry, str)
                else entry.get("_description", entry.get(""))
              )
              self.assertEqual(displayed.get(token), expected)

  @staticmethod
  def _static_help_children(prefix):
    node = COMMANDS
    for token in prefix:
      if not isinstance(node, dict) or token not in node:
        return ()
      node = node[token]
    if not isinstance(node, dict):
      return ()
    children = [
      (token, entry)
      for token, entry in node.items()
      if token and not token.startswith("_")
    ]
    switches = node.get("_switches", {})
    if isinstance(switches, dict):
      children += list(switches.items())
    return children

  def test_description_metadata_never_makes_parent_executable(self):
    """Adding help must not silently change command legality."""
    with tempfile.TemporaryDirectory() as td:
      context = Context(Path(td), legal_only=False)
      with self.assertRaises(CommandGrammarError):
        parse_tokens(COMMANDS, context, ("lanes",))
      with self.assertRaises(CommandGrammarError):
        parse_tokens(COMMANDS, context, ("workspace",))
      self.assertEqual(
        parse_tokens(COMMANDS, context, ("lanes", "clear")),
        ("lanes", "clear"),
      )

  def test_dynamic_help_and_argument_hints_are_described(self):
    """Dynamic command choices and parameter hints need usable help too."""
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)
      cases = (
        (("test",), ("RED", "temporary", "GREEN", "regression", "integration", "results")),
        (("high-risk",), ("<value>",)),
        (("issue", "start"), ("<value>",)),
        (("lanes", "select"), ("<value>",)),
      )
      for prefix, names in cases:
        with self.subTest(prefix=prefix):
          result = self.run_cli(root, *prefix, "--help")
          self.assertEqual(result.returncode, 0, result.stderr)
          rows = {
            parts[0]: parts[1]
            for line in result.stdout.splitlines()
            if len(parts := line.split(maxsplit=1)) == 2
          }
          for name in names:
            self.assertIn(name, rows)
            self.assertTrue(rows[name].strip())

  def test_lanes_help_describes_nested_public_commands(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)

      completed = self.run_cli(root, "lanes", "--help")
      self.assertEqual(completed.returncode, 0, completed.stderr)
      lines = {
        line.split(maxsplit=1)[0]: line.split(maxsplit=1)[1]
        for line in completed.stdout.splitlines()
      }
      self.assertEqual(
        lines["list"],
        "List selected issues grouped by lane",
      )
      self.assertEqual(
        lines["select"],
        "Select issue focus roots",
      )
      self.assertEqual(
        lines["view"],
        "Render selected dependency topology",
      )

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

  def test_read_only_queries_run_through_discovered_github_adapter(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
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

      bin_dir = base / "bin"
      bin_dir.mkdir()
      gh = bin_dir / "gh"
      gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['issue', 'list']:\n"
        "  print(json.dumps([{'number': 297, 'title': 'Bootstrap help'}]))\n"
        "elif args[:2] == ['issue', 'view']:\n"
        "  number = int(args[2])\n"
        "  if number == 207:\n"
        "    print(json.dumps({'number': number, 'title': 'Merged PR', "
        "'state': 'MERGED', 'url': "
        "f'https://github.com/Ma-XX-oN/RepoWorkflow/pull/{number}'}))\n"
        "  else:\n"
        "    print(json.dumps({'number': number, 'title': 'Bootstrap help', "
        "'state': 'OPEN', 'url': "
        "f'https://github.com/Ma-XX-oN/RepoWorkflow/issues/{number}'}))\n"
        "else:\n"
        "  print('unexpected gh arguments: ' + repr(args), file=sys.stderr)\n"
        "  raise SystemExit(2)\n",
        encoding="utf-8",
      )
      gh.chmod(0o755)
      env = dict(os.environ)
      env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

      listed = self.run_cli(root, "issue", "list", env=env)
      self.assertEqual(listed.returncode, 0, listed.stderr)
      self.assertEqual(listed.stdout.strip(), "#297  Bootstrap help")

      info = self.run_cli(root, "issue", "info", "297", env=env)
      self.assertEqual(info.returncode, 0, info.stderr)
      self.assertEqual(
        info.stdout.strip(),
        "#297  Bootstrap help  open  "
        "https://github.com/Ma-XX-oN/RepoWorkflow/issues/297",
      )

      pull_request = self.run_cli(root, "issue", "info", "207", env=env)
      self.assertEqual(pull_request.returncode, 2)
      self.assertIn(
        "#207 is a pull request, not an issue",
        pull_request.stderr,
      )
      self.assertNotIn("invalid issue state", pull_request.stderr)

  def test_expected_public_precondition_failures_never_traceback(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)
      identity = dict(os.environ)
      identity["RWF_WRITER_ID"] = "human"
      identity["RWF_SESSION_ID"] = "session"

      cases = [
        (
          ("lanes", "select", "206"),
          identity,
          "no GitHub remote could be discovered",
        ),
        (
          ("lanes", "list"),
          None,
          "lane selection is missing",
        ),
        (
          ("lanes", "view"),
          None,
          "lane selection is missing",
        ),
        (
          ("lanes", "clear"),
          identity,
          "lane selection is missing",
        ),
        (
          ("workspace", "create", "140"),
          None,
          "has no registered canonical relationships",
        ),
        (
          ("workspace", "info"),
          None,
          "workspace must be specified",
        ),
        (
          ("issue", "64", "dependency", "from-tickets"),
          None,
          "missing RepoWorkflow configuration",
        ),
      ]
      for words, env, message in cases:
        with self.subTest(words=words):
          completed = self.run_cli(root, *words, env=env)
          self.assertEqual(completed.returncode, 2, completed.stderr)
          self.assertTrue(
            completed.stderr.startswith("RepoWorkflow error:"),
            completed.stderr,
          )
          self.assertIn(message, completed.stderr)
          self.assertNotIn("Traceback (most recent call last)", completed.stderr)

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
