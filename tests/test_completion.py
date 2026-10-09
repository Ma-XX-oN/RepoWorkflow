from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest

from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]


class BashCompletionTests(unittest.TestCase):
  def make(self, *, registered=True):
    td = tempfile.TemporaryDirectory()
    base = Path(td.name)
    root = base / "repo"
    root.mkdir()
    fx = RepoFixture(root)
    groups = {
      "issue-2-wrong": {"type": "regression", "name": "tests.test_self_ci"},
    }
    if registered:
      groups["issue-1-red"] = {
        "type": "regression", "name": "tests.test_self_ci",
      }
    (root / ".ci/tests.json").write_text(json.dumps({
      "test-harnesses": {
        "unittest": {
          "command": "python",
          "layout": ["-m", "unittest", "$test"],
        },
      },
      "tests": [{"test-harness": "unittest", **groups}],
      "aliases": {},
    }))
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
      ["bash", "-c", script], capture_output=True, text=True,
    )

  def test_aliases_are_registered_without_filename_fallback(self):
    td, root, fx, wrapper = self.make()
    with td:
      result = self.run_bash(
        root, wrapper, "complete -p repo-workflow\ncomplete -p rwf\n",
      )
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertIn("-F _repo_workflow_complete repo-workflow", result.stdout)
      self.assertIn("-F _repo_workflow_complete rwf", result.stdout)
      self.assertNotIn("-o default", result.stdout)

  def test_red_completion_only_offers_current_issue_group(self):
    td, root, fx, wrapper = self.make()
    with td:
      result = self.run_bash(
        root, wrapper,
        'COMP_WORDS=(rwf test RED "")\n'
        "COMP_CWORD=3\n_repo_workflow_complete\n"
        'printf "REPLY:%s\\n" "${COMPREPLY[@]}"\n',
      )
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(
        [line for line in result.stdout.splitlines() if line.startswith("REPLY:")],
        ["REPLY:issue-1-red"],
      )
      self.assertNotIn("issue-2-wrong", result.stdout)

  def test_no_red_group_explains_registration_requirement(self):
    td, root, fx, wrapper = self.make(registered=False)
    with td:
      result = self.run_bash(
        root, wrapper,
        'COMP_WORDS=(rwf test RED "")\n'
        "COMP_CWORD=3\n_repo_workflow_complete\n"
        'printf "COUNT:%s\\n" "${#COMPREPLY[@]}"\n',
      )
      self.assertEqual(result.returncode, 0)
      self.assertIn("COUNT:0", result.stdout)
      self.assertIn("RED/GREEN tests do not exist", result.stderr)
      self.assertIn(".ci/tests.json", result.stderr)
      self.assertIn("issue-N-", result.stderr)

  def test_double_tab_describes_current_issue_red_group(self):
    td, root, fx, wrapper = self.make()
    with td:
      result = self.run_bash(
        root, wrapper,
        'COMP_WORDS=(rwf test RED "")\n'
        "COMP_CWORD=3\n_repo_workflow_complete\n"
        "_repo_workflow_complete\n"
        'printf "COUNT:%s\\n" "${#COMPREPLY[@]}"\n',
      )
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertIn("issue-1-red", result.stdout)
      self.assertIn("Run current issue RED test group", result.stdout)
      self.assertIn("COUNT:0", result.stdout)

  def test_changed_red_prefix_resets_double_tab_state(self):
    td, root, fx, wrapper = self.make()
    with td:
      result = self.run_bash(
        root, wrapper,
        'COMP_WORDS=(rwf test RED "")\n'
        "COMP_CWORD=3\n_repo_workflow_complete >/dev/null\n"
        'COMP_WORDS=(rwf test RED issue-1-r)\n'
        "COMP_CWORD=3\n_repo_workflow_complete >/dev/null\n"
        'printf "REPLY:%s\\n" "${COMPREPLY[@]}"\n',
      )
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(result.stdout.splitlines(), ["REPLY:issue-1-red"])


if __name__ == "__main__":
  unittest.main()
