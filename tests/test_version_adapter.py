from pathlib import Path
import json
import sys
import tempfile
import unittest

from repo_workflow.config import load_config
from repo_workflow.version_adapter import (
  VersionAdapterError,
  read_development_version,
  read_stable_version,
  read_version,
  run_transition,
)
from tests.support import RepoFixture


class VersionAdapterTests(unittest.TestCase):
  def test_query_accepts_task_and_stable_namespaces(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      config = load_config(root)
      self.assertEqual(read_version(root, config), "1.0.0-issue.1.0.1")
      (root / "VERSION").write_text("1.2.3\n")
      self.assertEqual(read_version(root, config), "1.2.3")

  def test_task_transitions_are_semantic(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)
      config = load_config(root)

      self.assertEqual(read_development_version(root, config), "1.0.0-issue.1.0.1")
      run_transition(root, config, "task", "--increment", "CI-iteration")
      self.assertEqual(read_development_version(root, config), "1.0.0-issue.1.0.2")
      run_transition(root, config, "task", "--increment", "merge-integration-failed")
      self.assertEqual(read_development_version(root, config), "1.0.0-issue.1.1.1")

  def test_task_issue_transition_is_forwarded(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)
      (root / "VERSION").write_text("1.2.3\n")
      config = load_config(root)
      run_transition(root, config, "task", "--issue", "27")
      self.assertEqual(read_development_version(root, config), "1.2.3-issue.27.0.1")

  def test_stable_transitions_are_derived_by_consumer_adapter(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)
      (root / "VERSION").write_text("1.2.3\n")
      config = load_config(root)

      self.assertEqual(read_stable_version(root, config), "1.2.3")
      run_transition(root, config, "integrate", "--increment", "patch")
      self.assertEqual(read_stable_version(root, config), "1.2.4")
      (root / "VERSION").write_text("1.2.3\n")
      run_transition(root, config, "integrate", "--increment", "minor")
      self.assertEqual(read_stable_version(root, config), "1.3.0")
      (root / "VERSION").write_text("1.2.3\n")
      run_transition(root, config, "release-major")
      self.assertEqual(read_stable_version(root, config), "2.0.0")

  def test_query_must_not_modify_worktree(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      script = root / "scripts" / "bad-version.py"
      script.write_text(
        "from pathlib import Path\n"
        "Path('side-effect.txt').write_text('bad')\n"
        "print(Path('VERSION').read_text().strip())\n"
      )
      config_path = root / ".ci" / "repoworkflow.json"
      value = json.loads(config_path.read_text())
      value["versionCommand"] = [sys.executable, "scripts/bad-version.py"]
      config_path.write_text(json.dumps(value, indent=2) + "\n")
      fx.commit("install invalid version adapter")
      with self.assertRaisesRegex(VersionAdapterError, "modified the worktree"):
        read_development_version(root, load_config(root))

  def test_transition_must_not_move_head_or_refs(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      script = root / "scripts" / "bad-transition.py"
      script.write_text(
        "import subprocess\n"
        "subprocess.run(['git', 'tag', 'bad-side-effect'], check=True)\n"
      )
      config_path = root / ".ci" / "repoworkflow.json"
      value = json.loads(config_path.read_text())
      value["versionCommand"] = [sys.executable, "scripts/bad-transition.py"]
      config_path.write_text(json.dumps(value, indent=2) + "\n")
      fx.commit("install ref-mutating version adapter")
      with self.assertRaisesRegex(VersionAdapterError, "local Git refs"):
        run_transition(root, load_config(root), "task", "--increment", "CI-iteration")


if __name__ == "__main__":
  unittest.main()
