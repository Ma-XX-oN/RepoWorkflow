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
  run_transition,
)
from tests.support import RepoFixture


class VersionAdapterTests(unittest.TestCase):
  def test_task_transitions_are_semantic(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      config = load_config(root)

      self.assertEqual(read_development_version(root, config), "1.0.0-issue.1.0.1")
      run_transition(root, config, "task", "--increment", "CI-iteration")
      self.assertEqual(read_development_version(root, config), "1.0.0-issue.1.0.2")
      fx.commit("record CI iteration")
      run_transition(root, config, "task", "--increment", "merge-integration-failed")
      self.assertEqual(read_development_version(root, config), "1.0.0-issue.1.1.1")

  def test_stable_transitions_derive_literal_versions_in_adapter(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      (root / "VERSION").write_text("1.2.3\n")
      (root / ".ci" / "run-ci-request").write_text(fx.version + "\n\n")
      fx.commit("switch fixture to stable version")
      config = load_config(root)

      self.assertEqual(read_stable_version(root, config), "1.2.3")
      run_transition(root, config, "integrate", "--increment", "patch")
      self.assertEqual(read_stable_version(root, config), "1.2.4")
      fx._run("reset", "--hard", "HEAD")
      run_transition(root, config, "integrate", "--increment", "minor")
      self.assertEqual(read_stable_version(root, config), "1.3.0")
      fx._run("reset", "--hard", "HEAD")
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
      config_value = json.loads(config_path.read_text())
      config_value["versionCommand"] = [sys.executable, "scripts/bad-version.py"]
      config_path.write_text(json.dumps(config_value, indent=2) + "\n")
      fx.commit("install invalid version adapter")
      config = load_config(root)

      with self.assertRaisesRegex(VersionAdapterError, "modified the worktree"):
        read_development_version(root, config)

  def test_initial_task_issue_transition_is_verified(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root, version="1.2.3")
      config = load_config(root)

      run_transition(root, config, "task", "--issue", "42")

      self.assertEqual(read_development_version(root, config), "1.2.3-issue.42.0.1")

  def test_malformed_adapter_output_is_rejected(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      script = root / "scripts" / "bad-version.py"
      script.write_text("print('not-a-version')\n", encoding="utf-8")
      config_path = root / ".ci" / "repoworkflow.json"
      value = json.loads(config_path.read_text())
      value["versionCommand"] = [sys.executable, "scripts/bad-version.py"]
      config_path.write_text(json.dumps(value, indent=2) + "\n")
      fx.commit("install malformed adapter")
      config = load_config(root)

      with self.assertRaisesRegex(VersionAdapterError, "valid development version"):
        read_development_version(root, config)

  def test_failed_transition_rolls_back_partial_worktree_mutation(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      original = (root / "VERSION").read_text()
      script = root / "scripts" / "bad-version.py"
      script.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "path = Path('VERSION')\n"
        "if len(sys.argv) == 1:\n"
        "  print(path.read_text().strip())\n"
        "else:\n"
        "  path.write_text('9.9.9-issue.9.9.9\\n')\n"
        "  raise SystemExit(1)\n",
        encoding="utf-8",
      )
      config_path = root / ".ci" / "repoworkflow.json"
      value = json.loads(config_path.read_text())
      value["versionCommand"] = [sys.executable, "scripts/bad-version.py"]
      config_path.write_text(json.dumps(value, indent=2) + "\n")
      fx.commit("install failing adapter")
      original = (root / "VERSION").read_text()
      config = load_config(root)

      with self.assertRaisesRegex(VersionAdapterError, "adapter failed"):
        run_transition(root, config, "task", "--increment", "CI-iteration")

      self.assertEqual((root / "VERSION").read_text(), original)
      self.assertEqual(fx._run("status", "--porcelain").stdout, "")

  def test_inconsistent_transition_is_rejected_and_rolled_back(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      script = root / "scripts" / "bad-version.py"
      script.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "path = Path('VERSION')\n"
        "if len(sys.argv) == 1:\n"
        "  print(path.read_text().strip())\n"
        "else:\n"
        "  path.write_text('1.0.0-issue.1.0.9\\n')\n",
        encoding="utf-8",
      )
      config_path = root / ".ci" / "repoworkflow.json"
      value = json.loads(config_path.read_text())
      value["versionCommand"] = [sys.executable, "scripts/bad-version.py"]
      config_path.write_text(json.dumps(value, indent=2) + "\n")
      fx.commit("install inconsistent adapter")
      original = (root / "VERSION").read_text()
      config = load_config(root)

      with self.assertRaisesRegex(VersionAdapterError, "inconsistent transition"):
        run_transition(root, config, "task", "--increment", "CI-iteration")

      self.assertEqual((root / "VERSION").read_text(), original)
      self.assertEqual(fx._run("status", "--porcelain").stdout, "")


if __name__ == "__main__":
  unittest.main()
