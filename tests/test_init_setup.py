import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from repo_workflow.init_setup import (
  BASHRC_BEGIN,
  InitError,
  discover_worktree,
  initialize,
)
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


class InitSetupTests(unittest.TestCase):
  def test_init_from_nested_directory_is_idempotent(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      home = base / "home"
      root.mkdir()
      home.mkdir()
      RepoFixture(root)
      nested = root / "a" / "b"
      nested.mkdir(parents=True)

      first = initialize(nested, ROOT, home=home)
      second = initialize(nested, ROOT, home=home)

      self.assertEqual(first.root, root.resolve())
      self.assertEqual(first.shell_file, second.shell_file)
      self.assertEqual(
        {path.name for path in first.hooks},
        {"pre-commit", "pre-push", "pre-rebase"},
      )
      bashrc = (home / ".bashrc").read_text(encoding="utf-8")
      self.assertEqual(bashrc.count(BASHRC_BEGIN), 1)
      for name in ("pre-commit", "pre-push", "pre-rebase"):
        self.assertTrue((root / ".git" / "hooks" / name).is_file())

  def test_sourceable_init_activates_same_shell_and_both_aliases(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      home = base / "home"
      root.mkdir()
      home.mkdir()
      fx = RepoFixture(root)
      _require_mit(root, fx)
      save_local_state(
        root,
        fx.head(),
        regression="PASS",
        automaticIntegration="PASS",
      )
      _write_launcher(root)
      nested = root / "nested"
      nested.mkdir()

      script = f"""
set -uo pipefail
export PYTHON={shlex.quote(_bash_path(Path(sys.executable)))}
cd {_bash_path(nested)!r}
source <({_bash_path(Path(sys.executable))!r} {_bash_path(ROOT / 'repo_workflow.py')!r} init --home {_bash_path(home)!r} --bash)
printf 'types:%s,%s\\n' "$(type -t rwf)" "$(type -t repo-workflow)"
printf 'short:%s\\n' "$(rwf version)"
printf 'long:%s\\n' "$(repo-workflow version)"
COMP_WORDS=(rwf validate integration \"\")
COMP_CWORD=3
_repo_workflow_complete
printf 'complete-short:%s\\n' "${{COMPREPLY[*]}}"
COMP_WORDS=(repo-workflow validate integration \"\")
COMP_CWORD=3
_repo_workflow_complete
printf 'complete-long:%s\\n' "${{COMPREPLY[*]}}"
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
          "types:function,function",
          f"short:{fx.version}",
          f"long:{fx.version}",
          "complete-short:failed succeeded",
          "complete-long:failed succeeded",
        ],
      )

  def test_same_shell_switches_between_repository_local_launchers(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      home = base / "home"
      home.mkdir()
      repos = []
      for name, marker_value in (("repo-a", "A"), ("repo-b", "B")):
        root = base / name
        root.mkdir()
        RepoFixture(root)
        launcher = root / "scripts" / "repoworkflow.py"
        launcher.write_text(
          "import sys\n"
          f"print({marker_value!r})\n",
          encoding="utf-8",
        )
        repos.append(root)

      first, second = repos
      script = f"""
set -uo pipefail
export PYTHON={shlex.quote(_bash_path(Path(sys.executable)))}
cd {_bash_path(first)!r}
source <({_bash_path(Path(sys.executable))!r} {_bash_path(ROOT / 'repo_workflow.py')!r} init --home {_bash_path(home)!r} --bash)
printf 'a-short:%s\\n' "$(rwf probe)"
cd {_bash_path(second)!r}
printf 'b-short:%s\\n' "$(rwf probe)"
printf 'b-long:%s\\n' "$(repo-workflow probe)"
cd {_bash_path(first)!r}
printf 'a-long:%s\\n' "$(repo-workflow probe)"
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
        ["a-short:A", "b-short:B", "b-long:B", "a-long:A"],
      )

  def test_discovery_rejects_plain_git_repository_without_rwf_config(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=root,
        check=True,
        capture_output=True,
      )

      with self.assertRaisesRegex(InitError, "not a RepoWorkflow consumer"):
        discover_worktree(root)

  def test_init_refuses_foreign_completion_file(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      home = base / "home"
      root.mkdir()
      home.mkdir()
      RepoFixture(root)
      target = home / ".config" / "repoworkflow" / "bash" / "repo-workflow.bash"
      target.parent.mkdir(parents=True)
      target.write_text("# foreign shell setup\n", encoding="utf-8")

      with self.assertRaisesRegex(InitError, "not RepoWorkflow-managed"):
        initialize(root, ROOT, home=home)
      self.assertEqual(
        target.read_text(encoding="utf-8"),
        "# foreign shell setup\n",
      )

  def test_discovery_outside_git_worktree_is_actionable(self):
    with tempfile.TemporaryDirectory() as td:
      with self.assertRaisesRegex(InitError, "not inside a Git worktree"):
        discover_worktree(Path(td))


if __name__ == "__main__":
  unittest.main()
