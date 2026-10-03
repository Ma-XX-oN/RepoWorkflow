from pathlib import Path
import os
import subprocess
import tempfile
import unittest

from repo_workflow.workflow_state import save_local_state
from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]


class BashCompletionTests(unittest.TestCase):
  def make(self, *, regression="PASS"):
    td = tempfile.TemporaryDirectory()
    base = Path(td.name)
    root = base / "repo"
    root.mkdir()
    fx = RepoFixture(root)
    save_local_state(root, fx.head(), regression=regression, integrationResult=None)

    wrapper = base / "repo-workflow"
    wrapper.write_text(
      "#!/usr/bin/env bash\n"
      f"exec {subprocess.list2cmdline([os.fspath(Path(os.sys.executable))])} "
      f"{subprocess.list2cmdline([os.fspath(ROOT / 'repo_workflow.py')])} \"$@\"\n",
      encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return td, root, fx, wrapper

  def run_bash(self, root: Path, wrapper: Path, body: str):
    script = f"""
set -euo pipefail
export REPO_WORKFLOW_COMMAND={subprocess.list2cmdline([os.fspath(wrapper)])}
export REPO_WORKFLOW_ROOT={subprocess.list2cmdline([os.fspath(root)])}
source {subprocess.list2cmdline([os.fspath(ROOT / 'completions' / 'repo-workflow.bash')])}
{body}
"""
    return subprocess.run(
      ["bash", "-c", script],
      capture_output=True,
      text=True,
    )

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
        root,
        wrapper,
        'COMP_WORDS=(rwf validate integration "")\n'
        "COMP_CWORD=3\n"
        "_repo_workflow_complete\n"
        'printf "REPLY:%s\\n" "\${COMPREPLY[@]}"\n',
      )
      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertIn("<last-terminal>", completed.stdout)
      replies = [
        line.removeprefix("REPLY:")
        for line in completed.stdout.splitlines()
        if line.startswith("REPLY:")
      ]
      self.assertEqual(replies, ["failed", "succeeded"])

  def test_state_invalid_completion_prints_diagnostic_and_returns_no_reply(self):
    td, root, fx, wrapper = self.make(regression="missing")
    with td:
      before = (root / "VERSION").read_text()
      completed = self.run_bash(
        root,
        wrapper,
        'COMP_WORDS=(rwf validate integration s)\n'
        "COMP_CWORD=3\n"
        "_repo_workflow_complete\n"
        'printf "COUNT:%s\\n" "\${#COMPREPLY[@]}"\n',
      )
      self.assertEqual(completed.returncode, 0)
      self.assertIn("COUNT:0", completed.stdout)
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
      self.assertEqual((root / "VERSION").read_text(), before)

  def test_second_tab_shows_descriptions_and_returns_no_replies(self):
    td, root, fx, wrapper = self.make()
    with td:
      completed = self.run_bash(
        root,
        wrapper,
        'COMP_WORDS=(rwf validate integration "")\n'
        "COMP_CWORD=3\n"
        "_repo_workflow_complete\n"
        "_repo_workflow_complete\n"
        'printf "COUNT:%s\\n" "\${#COMPREPLY[@]}"\n',
      )
      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertIn("failed", completed.stdout)
      self.assertIn("Report integration tests failed", completed.stdout)
      self.assertIn("succeeded", completed.stdout)
      self.assertIn("Report integration tests succeeded", completed.stdout)
      self.assertIn("COUNT:0", completed.stdout)

  def test_changed_completion_context_resets_double_tab_state(self):
    td, root, fx, wrapper = self.make()
    with td:
      completed = self.run_bash(
        root,
        wrapper,
        'COMP_WORDS=(rwf validate integration "")\n'
        "COMP_CWORD=3\n"
        "_repo_workflow_complete >/dev/null\n"
        'COMP_WORDS=(rwf validate integration f)\n'
        "COMP_CWORD=3\n"
        "_repo_workflow_complete >/dev/null\n"
        'printf "REPLY:%s\\n" "\${COMPREPLY[@]}"\n',
      )
      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertEqual(completed.stdout.splitlines(), ["REPLY:failed"])


if __name__ == "__main__":
  unittest.main()
