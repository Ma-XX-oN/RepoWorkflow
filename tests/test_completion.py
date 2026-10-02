import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from repo_workflow.workflow_state import save_local_state
from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]

def _bash_path(path: Path) -> str:
  value = str(path.resolve())
  if os.name != "nt":
    return value
  drive = value[0].lower()
  rest = value[2:].replace("\\", "/")
  return f"/{drive}{rest}"




def _bash_executable() -> str:
  if os.name != "nt":
    value = shutil.which("bash")
    if not value:
      raise RuntimeError("Bash is unavailable")
    return value
  git = shutil.which("git")
  if not git:
    raise RuntimeError("Git is unavailable")
  git_path = Path(git).resolve()
  candidates = (
    git_path.parent / "bash.exe",
    git_path.parent.parent / "bin" / "bash.exe",
  )
  for candidate in candidates:
    if candidate.is_file():
      return str(candidate)
  raise RuntimeError("Git for Windows Bash is unavailable")


def _require_mit(root: Path, fx: RepoFixture) -> None:
  path = root / ".ci" / "repoworkflow.json"
  config = json.loads(path.read_text(encoding="utf-8"))
  config["manualIntegrationRequired"] = True
  path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
  fx.commit("require manual integration")


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
      _require_mit(root, fx)
      save_local_state(
        root,
        fx.head(),
        regression="PASS",
        automaticIntegration="PASS",
      )
      _write_launcher(root)
      nested = root / "nested" / "dir"
      nested.mkdir(parents=True)

      script = f"""
set -uo pipefail
export PYTHON={shlex.quote(_bash_path(Path(sys.executable)))}
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
exit 0
"""
      completed = subprocess.run(
        [_bash_executable(), "-c", script],
        check=False,
        capture_output=True,
        text=True,
      )
      self.assertEqual(completed.returncode, 0, completed.stderr)
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
      _require_mit(root, fx)
      save_local_state(
        root,
        fx.head(),
        regression="PASS",
        automaticIntegration="PASS",
      )

      script = f"""
set -uo pipefail
export PYTHON={shlex.quote(_bash_path(Path(sys.executable)))}
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
exit 0
"""
      completed = subprocess.run(
        [_bash_executable(), "-c", script],
        check=False,
        capture_output=True,
        text=True,
      )
      self.assertEqual(completed.returncode, 0, completed.stderr)

      self.assertEqual(
        completed.stdout.splitlines(),
        ["partial:succeeded", "option:--json"],
      )
      self.assertFalse(marker_path.exists())
      self.assertEqual(fx._run("status", "--porcelain").stdout, "")


if __name__ == "__main__":
  unittest.main()
