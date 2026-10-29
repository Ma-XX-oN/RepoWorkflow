from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

from repo_workflow.public_commands import COMMANDS
from repo_workflow.repo_info_adapter import resolve_info_config
from repo_workflow.ticket_dependency_adapter import resolve_dependency_config


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



from tests.p4_provider_fixture import (
  FIXTURE, configure_provider, provider_calls, verify_provider,
)


class BootstrapCliTests(unittest.TestCase):
  def make_repo(self, root: Path) -> None:
    subprocess.run(
      ["git", "init", "-b", "main"],
      cwd=root,
      check=True,
      capture_output=True,
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
    )

  def run_cli(self, root: Path, *args: str, env=None):
    if env is not None and "RWF_TEST_FIXTURE_BASE" in env:
      verify_provider(root, env)
    return subprocess.run(
      [sys.executable, str(CLI), "--root", str(root), *args],
      capture_output=True,
      text=True,
      env=env, encoding="utf-8", errors="strict",
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
        cwd=root, check=True, capture_output=True,
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

  def test_read_only_queries_run_through_configured_provider(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = configure_provider(base, {297: [], 207: []}, {
        297: "Bootstrap help", 207: "Merged PR",
      })
      metadata = Path(env["RWF_TEST_META"])
      value = json.loads(metadata.read_text(encoding="utf-8"))
      value["207"].update({
        "state": "MERGED",
        "url": "https://github.com/Ma-XX-oN/RepoWorkflow/pull/207",
      })
      metadata.write_text(json.dumps(value), encoding="utf-8")
      verify_provider(root, env)

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
      self.assertIn("#207 is a pull request, not an issue", pull_request.stderr)
      self.assertNotIn("invalid issue state", pull_request.stderr)
      self.assertNotIn("GH_TOKEN", env)
      self.assertNotIn("GITHUB_TOKEN", env)
      self.assertEqual(provider_calls(env), [
        {"kind": "info", "args": ["issue", "list-open"]},
        {"kind": "info", "args": ["issue", "get", "297"]},
        {"kind": "info", "args": ["issue", "get", "207"]},
      ])
      unexpected = subprocess.run(
        [sys.executable, str(FIXTURE), "info", str(base), "pr", "list"],
        capture_output=True, text=True, encoding="utf-8",
      )
      self.assertEqual(unexpected.returncode, 2)
      self.assertIn("unexpected provider arguments", unexpected.stderr)
      self.assertEqual(provider_calls(env)[-1], {
        "kind": "info", "args": ["pr", "list"],
      })

  def test_provider_guard_rejects_actual_gh_even_with_python_optimization(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = configure_provider(base, {201: []})
      config_path = root / ".ci" / "repoworkflow.json"
      data = json.loads(config_path.read_text(encoding="utf-8"))
      data["infoCommand"] = ["gh", "issue", "view", "201"]
      config_path.write_text(json.dumps(data), encoding="utf-8")
      for optimized in (False, True):
        with self.subTest(optimized=optimized):
          invocation = [
            sys.executable, *(["-O"] if optimized else []), "-c",
            "import os; from pathlib import Path; "
            "from tests.p4_provider_fixture import verify_provider; "
            "verify_provider(Path(os.environ['RWF_TEST_FIXTURE_BASE']) / "
            "'repo', os.environ)",
          ]
          rejected = subprocess.run(
            invocation, env=env, capture_output=True, text=True,
            encoding="utf-8",
          )
          self.assertNotEqual(rejected.returncode, 0)
          self.assertIn("nonhermetic infoCommand", rejected.stderr)
      with self.assertRaisesRegex(RuntimeError, "nonhermetic infoCommand"):
        self.run_cli(root, "issue", "info", "201", env=env)
      self.assertEqual(provider_calls(env), [])

  def test_provider_guard_rejects_dependency_fallback_with_optimization(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = configure_provider(base, {201: []})
      config_path = root / ".ci" / "repoworkflow.json"
      data = json.loads(config_path.read_text(encoding="utf-8"))
      data["dependencyCommand"] = ["gh", "issue", "view", "201"]
      config_path.write_text(json.dumps(data), encoding="utf-8")
      for optimized in (False, True):
        with self.subTest(optimized=optimized):
          command = [
            sys.executable, *(["-O"] if optimized else []), "-c",
            "import os; from pathlib import Path; "
            "from tests.p4_provider_fixture import verify_provider; "
            "verify_provider(Path(os.environ['RWF_TEST_FIXTURE_BASE']) / "
            "'repo', os.environ)",
          ]
          result = subprocess.run(
            command, env=env, capture_output=True, text=True,
            encoding="utf-8",
          )
          self.assertNotEqual(result.returncode, 0)
          self.assertIn("nonhermetic dependencyCommand", result.stderr)
      with self.assertRaisesRegex(RuntimeError, "dependencyCommand"):
        self.run_cli(root, "lanes", "view", env=env)
      self.assertEqual(provider_calls(env), [])

  def test_provider_guard_refuses_secret_and_path_shadow(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = configure_provider(base, {201: []})
      env["GH_TOKEN"] = "forbidden-fixture-secret"
      with self.assertRaisesRegex(RuntimeError, "credentials are forbidden"):
        self.run_cli(root, "issue", "list", env=env)
      env.pop("GH_TOKEN")
      (base / "bin").mkdir()
      with self.assertRaisesRegex(RuntimeError, "shadowing is forbidden"):
        self.run_cli(root, "issue", "list", env=env)
      self.assertEqual(provider_calls(env), [])

  def test_default_github_provider_discovery_without_execution(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)
      subprocess.run(
        ["git", "remote", "add", "origin",
         "https://github.com/Ma-XX-oN/RepoWorkflow.git"],
        cwd=root, check=True,
      )
      info = resolve_info_config(root)
      dependency = resolve_dependency_config(root)
      self.assertEqual(info["infoCommand"][0], sys.executable)
      self.assertEqual(dependency["dependencyCommand"][0], sys.executable)
      self.assertEqual(
        Path(info["infoCommand"][1]).name, "repo-info-github.py",
      )
      self.assertEqual(
        Path(dependency["dependencyCommand"][1]).name,
        "github-ticket-dependencies.py",
      )
      self.assertTrue(Path(info["infoCommand"][1]).is_file())
      self.assertTrue(Path(dependency["dependencyCommand"][1]).is_file())
      # Deliberately resolve only: default executables are NOT run here.

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
