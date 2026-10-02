import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

from repo_workflow.workflow_state import save_local_state
from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]

def _bash_path(path: Path) -> str:
  if sys.platform != "win32":
    return str(path)
  return subprocess.check_output(
    ["bash", "-lc", 'cygpath -u "$1"', "bash", str(path)],
    text=True,
  ).strip()



def _bash_path(path: Path) -> str:
  value = str(path.resolve())
  if os.name != "nt":
    return value
  drive = value[0].lower()
  rest = value[2:].replace("\\", "/")
  return f"/{drive}{rest}"


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
cd {_bash_path(nested)!r}
source {_bash_path(ROOT / 'completions' / 'repo-workflow.bash')!r}
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

  def test_completion_partial_tokens_and_options_do_not_mutate_repository(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      marker_path = root / "validation-ran.txt"
      fx = RepoFixture(
        root,
        validation_body=(
          "from pathlib import Path\n"
          "Path('validation-ran.txt').write_text('ran')\n"
        ),
      )
      _write_launcher(root)
      (root / "succeeded-unrelated-file").write_text(
        "unrelated\n",
        encoding="utf-8",
      )
      fx.commit("add completion fixture files")
      save_local_state(
        root,
        fx.head(),
        regression="PASS",
        integrationResult=None,
      )

      script = f"""
set -euo pipefail
cd {_bash_path(root)!r}
source {_bash_path(ROOT / 'completions' / 'repo-workflow.bash')!r}
COMP_WORDS=(rwf validate integration s)
COMP_CWORD=3
_repo_workflow_complete
printf 'partial:%s\\n' "${{COMPREPLY[*]}}"
COMP_WORDS=(repo-workflow what-next --)
COMP_CWORD=2
_repo_workflow_complete
printf 'option:%s\\n' "${{COMPREPLY[*]}}"
"""
      completed = subprocess.run(
        ["bash", "-c", script],
        check=True,
        capture_output=True,
        text=True,
      )

      self.assertEqual(
        completed.stdout.splitlines(),
        ["partial:succeeded", "option:--json"],
      )
      self.assertFalse(marker_path.exists())
      self.assertEqual(fx._run("status", "--porcelain").stdout, "")


if __name__ == "__main__":
  unittest.main()
