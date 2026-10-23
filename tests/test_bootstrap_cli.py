from pathlib import Path
import json
import os
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



def install_fake_gh(base: Path, env: dict[str, str], script: Path) -> Path:
  """Route Python subprocess gh calls to the local fixture on every OS."""
  hook_dir = base / "python-gh-hook"
  hook_dir.mkdir()
  (hook_dir / "sitecustomize.py").write_text(
    "import json, os, subprocess, sys\n"
    "_run = subprocess.run\n"
    "def _fake_gh(arguments, *args, **kwargs):\n"
    "  if isinstance(arguments, (list, tuple)) and arguments and arguments[0] == 'gh':\n"
    "    with open(os.environ['RWF_FAKE_GH_ROUTES'], 'a', encoding='utf-8') as log:\n"
    "      log.write(json.dumps(list(arguments[1:])) + '\\n')\n"
    "    return _run([sys.executable, os.environ['RWF_FAKE_GH_SCRIPT'], *arguments[1:]], *args, **kwargs)\n"
    "  return _run(arguments, *args, **kwargs)\n"
    "subprocess.run = _fake_gh\n",
    encoding="utf-8",
  )
  routes = base / "gh-routes.jsonl"
  routes.write_text("", encoding="utf-8")
  env["RWF_FAKE_GH_SCRIPT"] = str(script)
  env["RWF_FAKE_GH_ROUTES"] = str(routes)
  env["PYTHONPATH"] = os.pathsep.join(
    (str(hook_dir), env.get("PYTHONPATH", "")),
  )
  env.pop("GH_TOKEN", None)
  env.pop("GITHUB_TOKEN", None)
  return routes

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
        if prefix == ("test", "RED"):
          continue  # RED help requires a current issue and registered groups.
        with self.subTest(prefix=prefix):
          completed = self.run_cli(root, *prefix, "--help")
          self.assertEqual(completed.returncode, 0, completed.stderr)
          self.assertNotIn("repoworkflow.json", completed.stderr)
          self.assertNotIn("missing RepoWorkflow configuration", completed.stderr)


  def test_red_help_uses_current_issue_catalogue_and_errors(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)
      # Absent started issue and catalogue: help must match shared completion.
      missing = self.run_cli(root, "test", "RED", "--help")
      missing_completion = self.run_cli(root, "complete", "test", "RED", "")
      self.assertNotEqual(missing.returncode, 0)
      self.assertEqual(missing.returncode, missing_completion.returncode)
      self.assertEqual(missing.stderr, missing_completion.stderr)

      subprocess.run(
        ["git", "checkout", "-b", "issue-297-help-fixture"],
        cwd=root, check=True, capture_output=True, text=True,
      )
      catalogue = root / ".ci" / "tests.json"
      catalogue.parent.mkdir()
      value = {
        "test-harnesses": {
          "unittest": {"command": "python", "layout": ["-m", "unittest", "$test"]},
        },
        "tests": [{
          "test-harness": "unittest",
          "issue-297-current": {
            "type": "regression", "name": "tests.test_bootstrap_cli",
          },
          "issue-296-other": {
            "type": "regression", "name": "tests.test_bootstrap_cli",
          },
        }],
      }
      catalogue.write_text(json.dumps(value), encoding="utf-8")
      current = self.run_cli(root, "test", "RED", "--help")
      single = self.run_cli(root, "complete", "test", "RED", "")
      self.assertEqual(current.returncode, 0, current.stderr)
      self.assertEqual(single.returncode, 0, single.stderr)
      self.assertIn("issue-297-current", current.stdout)
      self.assertNotIn("issue-296-other", current.stdout)
      self.assertEqual(
        [line.split(" - ", 1)[0] for line in current.stdout.splitlines()],
        single.stdout.splitlines(),
      )

      value["tests"][0].pop("issue-297-current")
      catalogue.write_text(json.dumps(value), encoding="utf-8")
      absent = self.run_cli(root, "test", "RED", "--help")
      absent_completion = self.run_cli(root, "complete", "test", "RED", "")
      self.assertNotEqual(absent.returncode, 0)
      self.assertEqual(absent.returncode, absent_completion.returncode)
      self.assertEqual(absent.stderr, absent_completion.stderr)
      self.assertIn("RED/GREEN tests do not exist", absent.stderr)

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
        "if args == ['issue', 'list', '--state', 'open', '--limit', '1000', '--json', 'number,title', '--repo', 'Ma-XX-oN/RepoWorkflow']:\n"
        "  print(json.dumps([{'number': 297, 'title': 'Bootstrap help'}]))\n"
        "elif len(args) == 7 and args[:2] == ['issue', 'view'] and args[3:] == ['--json', 'number,title,state,url', '--repo', 'Ma-XX-oN/RepoWorkflow']:\n"
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
      routes = install_fake_gh(base, env, gh)

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
      self.assertNotIn("GH_TOKEN", env)
      self.assertNotIn("GITHUB_TOKEN", env)
      self.assertEqual(
        [json.loads(line) for line in routes.read_text(encoding="utf-8").splitlines()],
        [
          ["issue", "list", "--state", "open", "--limit", "1000",
           "--json", "number,title", "--repo", "Ma-XX-oN/RepoWorkflow"],
          ["issue", "view", "297", "--json", "number,title,state,url",
           "--repo", "Ma-XX-oN/RepoWorkflow"],
          ["issue", "view", "207", "--json", "number,title,state,url",
           "--repo", "Ma-XX-oN/RepoWorkflow"],
        ],
      )
      bad = subprocess.run(
        [sys.executable, str(gh), "pr", "list"],
        capture_output=True, text=True, env=env,
      )
      self.assertEqual(bad.returncode, 2)
      self.assertIn("unexpected gh arguments", bad.stderr)

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
