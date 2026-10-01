from pathlib import Path
import subprocess
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
      save_local_state(
        root,
        fx.head(),
        regression="PASS",
        integrationResult=None,
      )
      _write_launcher(root)
      nested = root / "nested"
      nested.mkdir()

      script = f"""
set -euo pipefail
cd {str(nested)!r}
source <({str(Path(subprocess.check_output(['which', 'python3'], text=True).strip()))!r} {str(ROOT / 'repo_workflow.py')!r} init --home {str(home)!r} --bash)
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
          "types:function,function",
          f"short:{fx.version}",
          f"long:{fx.version}",
          "complete-short:failed succeeded",
          "complete-long:failed succeeded",
        ],
      )

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
