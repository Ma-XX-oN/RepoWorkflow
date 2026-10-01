from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.workflow_state import save_local_state
from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]


def _write_launcher(root: Path) -> None:
  launcher = root / "scripts" / "repoworkflow.py"
  launcher.write_text(
    "import subprocess\n"
    "import sys\n"
    f"raise SystemExit(subprocess.call([sys.executable, {str(ROOT / 'repo_workflow.py')!r}, *sys.argv[1:]]))\n",
    encoding="utf-8",
  )


class BashCompletionTests(unittest.TestCase):
  def test_bash_completion_invokes_same_projection_for_both_names(self):
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
      _write_launcher(root)
      nested = root / "nested" / "dir"
      nested.mkdir(parents=True)

      script = f"""
set -euo pipefail
cd {str(nested)!r}
source {str(ROOT / 'completions' / 'repo-workflow.bash')!r}
COMP_WORDS=(rwf validate integration \"\")
COMP_CWORD=3
_repo_workflow_complete
printf 'short:%s\\n' \"${{COMPREPLY[*]}}\"
COMP_WORDS=(repo-workflow validate integration \"\")
COMP_CWORD=3
_repo_workflow_complete
printf 'long:%s\\n' \"${{COMPREPLY[*]}}\"
COMP_WORDS=(rwf init --)
COMP_CWORD=2
_repo_workflow_complete
printf 'init:%s\\n' \"${{COMPREPLY[*]}}\"
"""
      completed = subprocess.run(
        ["bash", "-c", script],
        check=True,
        capture_output=True,
        text=True,
      )
      self.assertEqual(
        completed.stdout.splitlines(),
        [
          "short:failed succeeded",
          "long:failed succeeded",
          "init:--bash --force",
        ],
      )


if __name__ == "__main__":
  unittest.main()
