from pathlib import Path
import os
import subprocess
import tempfile
import unittest

from repo_workflow.workflow_state import save_local_state
from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]


class BashCompletionTests(unittest.TestCase):
  def test_bash_completion_invokes_state_machine_projection(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      save_local_state(
        root,
        fx.head(),
        regression="PASS",
        integrationResult=None,
      )

      wrapper = base / "repo-workflow"
      wrapper.write_text(
        "#!/usr/bin/env bash\n"
        f"exec {subprocess.list2cmdline([os.fspath(Path(os.sys.executable))])} "
        f"{subprocess.list2cmdline([os.fspath(ROOT / 'repo_workflow.py')])} \"$@\"\n",
        encoding="utf-8",
      )
      wrapper.chmod(0o755)

      script = f"""
set -euo pipefail
export REPO_WORKFLOW_COMMAND={subprocess.list2cmdline([os.fspath(wrapper)])}
export REPO_WORKFLOW_ROOT={subprocess.list2cmdline([os.fspath(root)])}
source {subprocess.list2cmdline([os.fspath(ROOT / 'completions' / 'repo-workflow.bash')])}
COMP_WORDS=(rwf validate integration \"\")
COMP_CWORD=3
_repo_workflow_complete
printf '%s\\n' \"${{COMPREPLY[@]}}\"
"""
      completed = subprocess.run(
        ["bash", "-c", script],
        check=True,
        capture_output=True,
        text=True,
      )
      self.assertEqual(completed.stdout.splitlines(), ["failed", "succeeded"])


if __name__ == "__main__":
  unittest.main()
