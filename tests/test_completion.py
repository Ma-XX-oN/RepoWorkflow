from pathlib import Path
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from repo_workflow.workflow_state import save_local_state
from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]


def working_bash():
  """Find a Bash that actually runs; ignore Windows WSL command shims."""
  choices = []
  # Prefer the Bash co-installed with Git over an unrelated PATH shim.
  git = shutil.which("git")
  if git:
    for parent in list(Path(git).resolve().parents)[:5]:
      choices.extend((parent / "bin" / "bash.exe",
                      parent / "usr" / "bin" / "bash.exe"))
  direct = shutil.which("bash")
  if direct:
    choices.append(Path(direct))
  seen = set()
  for path in choices:
    candidate = str(path)
    if candidate in seen or not path.is_file():
      continue
    seen.add(candidate)
    try:
      probe = subprocess.run(
        [candidate, "-c", "printf rwf-bash-ready"],
        capture_output=True, encoding="utf-8", errors="strict",
        timeout=8, check=False,
      )
    except (OSError, subprocess.TimeoutExpired):
      continue
    if probe.returncode == 0 and probe.stdout == "rwf-bash-ready":
      return candidate
  return None


def bash_path(executable, path: Path) -> str:
  """Bash resolves native cwd through its own OS boundary."""
  location = Path(path)
  result = subprocess.run(
    [executable, "-c", "pwd -P"], cwd=location.parent,
    capture_output=True, encoding="utf-8", errors="strict", check=True,
  )
  return result.stdout.removesuffix("\n") + "/" + location.name


class BashDiscoveryTests(unittest.TestCase):
  def test_failing_wsl_like_stub_is_not_accepted_as_bash(self):
    # A shim on PATH is not a shell capability merely because it exists.
    with mock.patch.object(shutil, "which", side_effect=lambda name: (
      sys.executable if name == "bash" else None
    )):
      with mock.patch.object(subprocess, "run", return_value=(
        subprocess.CompletedProcess(
          [sys.executable, "-c", "printf rwf-bash-ready"], 1,
          stdout="", stderr="WSL has no installed distributions",
        )
      )):
        self.assertIsNone(working_bash())

  def test_git_bash_wins_over_path_stub(self):
    with tempfile.TemporaryDirectory() as dirname:
      git_root = Path(dirname) / "Git"
      (git_root / "cmd").mkdir(parents=True)
      (git_root / "bin").mkdir()
      git = git_root / "cmd" / "git.exe"
      git.write_text("fixture", encoding="utf-8")
      git_bash = git_root / "bin" / "bash.exe"
      git_bash.write_text("fixture", encoding="utf-8")
      calls = []

      def probe(argv, **kwargs):
        calls.append(argv[0])
        return subprocess.CompletedProcess(
          argv, 0 if argv[0] == str(git_bash) else 1,
          stdout="rwf-bash-ready" if argv[0] == str(git_bash) else "",
          stderr="",
        )

      with mock.patch.object(shutil, "which", side_effect=lambda name: (
        str(git) if name == "git" else sys.executable
      )):
        with mock.patch.object(subprocess, "run", side_effect=probe):
          self.assertEqual(working_bash(), str(git_bash))
      self.assertEqual(calls, [str(git_bash)])

  def test_wrong_probe_output_is_not_accepted_as_bash(self):
    with mock.patch.object(shutil, "which", side_effect=lambda name: (
      sys.executable if name == "bash" else None
    )):
      with mock.patch.object(subprocess, "run", return_value=(
        subprocess.CompletedProcess(
          [sys.executable, "-c", "printf rwf-bash-ready"], 0,
          stdout="unexpected shell", stderr="",
        )
      )):
        self.assertIsNone(working_bash())


class BashCompletionTests(unittest.TestCase):
  def bash_path(self, path: Path) -> str:
    return bash_path(self.bash, path)

  def make(self, *, regression="PASS"):
    self.bash = working_bash()
    if self.bash is None:
      self.skipTest("No executable Bash passed the capability probe")
    td = tempfile.TemporaryDirectory(prefix="rwf Bash path with spaces ")

    base = Path(td.name)
    root = base / "repo"
    root.mkdir()
    fx = RepoFixture(root)
    save_local_state(root, fx.head(), regression=regression, integrationResult=None)

    wrapper = base / "repo-workflow"
    wrapper.write_text(
      "#!/usr/bin/env bash\n"
      + "exec " + shlex.quote(self.bash_path(Path(sys.executable)))
      + " " + shlex.quote(self.bash_path(ROOT / "repo_workflow.py"))
      + ' "$@"\n',
      encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return td, root, fx, wrapper

  def run_bash(self, root: Path, wrapper: Path, body: str):
    script = (
      "set -euo pipefail\n"
      + "export REPO_WORKFLOW_COMMAND="
      + shlex.quote(self.bash_path(wrapper)) + "\n"
      + "export REPO_WORKFLOW_ROOT="
      + shlex.quote(self.bash_path(root)) + "\n"
      + "source " + shlex.quote(
        self.bash_path(ROOT / "completions" / "repo-workflow.bash")
      ) + "\n"
      + body
    )
    return subprocess.run(
      [self.bash, "-c", script],
      capture_output=True, encoding="utf-8", errors="strict", check=False,
    )

  def test_exported_root_is_accessible_to_selected_bash(self):
    td, root, fx, wrapper = self.make()
    with td:
      completed = self.run_bash(
        root, wrapper,
        'test -d "$REPO_WORKFLOW_ROOT"\n'
        'test -f "$REPO_WORKFLOW_COMMAND"\n',
      )
      self.assertEqual(completed.returncode, 0, completed.stderr)

  def test_aliases_are_registered_without_filename_fallback(self):
    td, root, fx, wrapper = self.make()
    with td:
      completed = self.run_bash(
        root,
        wrapper,
        "complete -p repo-workflow\ncomplete -p rwf\n",
      )
      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertIn("-F _repo_workflow_complete repo-workflow", completed.stdout)
      self.assertIn("-F _repo_workflow_complete rwf", completed.stdout)
      self.assertNotIn("-o default", completed.stdout)
      self.assertNotIn("-o bashdefault", completed.stdout)

  def test_state_completion_uses_compreply_but_not_last_terminal(self):
    td, root, fx, wrapper = self.make()
    with td:
      completed = self.run_bash(
        root, wrapper,
        'COMP_WORDS=(rwf test "")\n'
        "COMP_CWORD=2\n"
        "_repo_workflow_complete\n"
        'printf "REPLY:%s\\n" "${COMPREPLY[@]}"\n',
      )
      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertIn("REPLY:integration", completed.stdout)
      self.assertIn("REPLY:regression", completed.stdout)
      self.assertNotIn("REPLY:<last-terminal>", completed.stdout)

  def test_state_invalid_completion_prints_diagnostic_and_returns_no_reply(self):
    td, root, fx, wrapper = self.make(regression="missing")
    with td:
      before = (root / "VERSION").read_text()
      completed = self.run_bash(
        root, wrapper,
        'COMP_WORDS=(rwf test invalid-stage)\n'
        "COMP_CWORD=2\n"
        "_repo_workflow_complete\n"
        'printf "COUNT:%s\\n" "${#COMPREPLY[@]}"\n',
      )
      self.assertEqual(completed.returncode, 0)
      self.assertIn("COUNT:0", completed.stdout)
      self.assertEqual((root / "VERSION").read_text(), before)

  def test_second_tab_shows_descriptions_and_returns_no_replies(self):
    td, root, fx, wrapper = self.make()
    with td:
      completed = self.run_bash(
        root, wrapper,
        'COMP_WORDS=(rwf test "")\n'
        "COMP_CWORD=2\n"
        "_repo_workflow_complete\n"
        "_repo_workflow_complete\n"
        'printf "COUNT:%s\\n" "${#COMPREPLY[@]}"\n',
      )
      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertIn("integration", completed.stdout)
      self.assertIn("Run integration tests locally", completed.stdout)
      self.assertIn("COUNT:0", completed.stdout)

  def test_changed_completion_context_resets_double_tab_state(self):
    td, root, fx, wrapper = self.make()
    with td:
      completed = self.run_bash(
        root, wrapper,
        'COMP_WORDS=(rwf test "")\n'
        "COMP_CWORD=2\n"
        "_repo_workflow_complete >/dev/null\n"
        'COMP_WORDS=(rwf test reg)\n'
        "COMP_CWORD=2\n"
        "_repo_workflow_complete >/dev/null\n"
        'printf "REPLY:%s\\n" "${COMPREPLY[@]}"\n',
      )
      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertEqual(completed.stdout.splitlines(), ["REPLY:regression"])

  def test_red_single_tab_and_double_tab_equal_direct_help(self):
    td, root, fx, wrapper = self.make()
    with td:
      catalogue = {
        "test-harnesses": {
          "unittest": {
            "command": "python", "layout": ["-m", "unittest", "$test"],
          },
        },
        "tests": [{
          "test-harness": "unittest",
          "issue-1-z": {"type": "regression", "name": "tests.test_completion"},
          "issue-1-a": {
            "type": "regression", "name": "tests.test_completion",
            "description": "Alpha case",
          },
        }],
      }
      (root / ".ci/tests.json").write_text(
        json.dumps(catalogue), encoding="utf-8",
      )
      completed = self.run_bash(
        root, wrapper,
        'COMP_WORDS=(rwf test RED "")\n'
        "COMP_CWORD=3\n"
        'COMP_LINE="rwf test RED "\n'
        "COMP_POINT=13\n"
        "_repo_workflow_complete\n"
        'printf "ONE:%s\\n" "${COMPREPLY[@]}"\n'
        "_repo_workflow_complete\n"
        'printf "COUNT:%s\\n" "${#COMPREPLY[@]}"\n',
      )
      self.assertEqual(completed.returncode, 0, completed.stderr)
      names = [x[4:] for x in completed.stdout.splitlines()
               if x.startswith("ONE:")]
      self.assertEqual(names, ["--remote", "issue-1-a", "issue-1-z"])
      self.assertIn("COUNT:0", completed.stdout)
      rendered = [x for x in completed.stdout.splitlines()
                  if not x.startswith(("ONE:", "COUNT:"))]
      helped = subprocess.run(
        [sys.executable, str(ROOT / "repo_workflow.py"),
         "--root", str(root), "test", "RED", "--help"],
        capture_output=True, encoding="utf-8", errors="strict",
      )
      self.assertEqual(helped.returncode, 0, helped.stderr)
      self.assertEqual(rendered, helped.stdout.splitlines())
      self.assertEqual(
        [x for x in rendered if x.startswith("issue-")],
        ["issue-1-a - Alpha case", "issue-1-z"],
      )

  def test_red_missing_groups_report_same_real_error(self):
    td, root, fx, wrapper = self.make()
    with td:
      completed = self.run_bash(
        root, wrapper,
        'COMP_WORDS=(rwf test RED "")\n'
        "COMP_CWORD=3\n"
        "_repo_workflow_complete\n"
        "_repo_workflow_complete\n"
        'printf "COUNT:%s\\n" "${#COMPREPLY[@]}"\n',
      )
      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertIn("COUNT:0", completed.stdout)
      self.assertIn("RED/GREEN tests do not exist", completed.stderr)
      helped = subprocess.run(
        [sys.executable, str(ROOT / "repo_workflow.py"),
         "--root", str(root), "test", "RED", "--help"],
        capture_output=True, encoding="utf-8", errors="strict",
      )
      self.assertEqual(helped.returncode, 2)
      self.assertEqual(helped.stderr.strip(),
                       completed.stderr.strip().splitlines()[-1])


if __name__ == "__main__":
  unittest.main()
