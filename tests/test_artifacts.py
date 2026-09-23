from pathlib import Path
import json
import sys
import tempfile
import unittest

from repo_workflow.artifacts import (
  ArtifactError,
  commit_artifact_changes,
  materialize_artifacts,
)
from repo_workflow.config import load_config
from tests.support import RepoFixture


class ArtifactTests(unittest.TestCase):
  def make(self, generator_body: str, verifier_body: str = "raise SystemExit(0)\n", *, platform="any"):
    td = tempfile.TemporaryDirectory()
    root = Path(td.name) / "repo"
    root.mkdir()
    artifact = {
      "id": "bundle",
      "generatorCommand": [sys.executable, "scripts/generate.py"],
      "verifierCommand": [sys.executable, "scripts/verify.py"],
      "outputs": ["dist/bundle.js"],
      "committed": True,
      "platform": platform,
      "capabilities": [],
    }
    fx = RepoFixture(root, artifacts=[artifact])
    (root / "scripts" / "generate.py").write_text(generator_body)
    (root / "scripts" / "verify.py").write_text(verifier_body)
    fx.commit("artifact scripts")
    fx.push()
    return td, root, fx

  def test_generator_may_change_only_declared_output(self):
    body = "from pathlib import Path\nPath('dist').mkdir(exist_ok=True)\nPath('dist/bundle.js').write_text('x')\n"
    td, root, _ = self.make(body)
    with td:
      result = materialize_artifacts(root, load_config(root))
      self.assertEqual(result.status, "PASS")
      self.assertEqual(result.changed_files, ["dist/bundle.js"])

  def test_generator_undeclared_path_is_rejected(self):
    body = "from pathlib import Path\nPath('oops.txt').write_text('x')\n"
    td, root, _ = self.make(body)
    with td:
      with self.assertRaisesRegex(ArtifactError, "undeclared path"):
        materialize_artifacts(root, load_config(root))

  def test_verifier_must_be_read_only(self):
    generator = "from pathlib import Path\nPath('dist').mkdir(exist_ok=True)\nPath('dist/bundle.js').write_text('x')\n"
    verifier = "from pathlib import Path\nPath('dist/bundle.js').write_text('changed')\n"
    td, root, _ = self.make(generator, verifier)
    with td:
      with self.assertRaisesRegex(ArtifactError, "verifier modified"):
        materialize_artifacts(root, load_config(root))

  def test_generator_exit_two_is_incomplete(self):
    td, root, _ = self.make("raise SystemExit(2)\n")
    with td:
      result = materialize_artifacts(root, load_config(root))
      self.assertEqual(result.status, "INCOMPLETE")

  def test_platform_mismatch_is_incomplete(self):
    mismatch = "windows" if not sys.platform.startswith("win") else "linux"
    td, root, _ = self.make("raise RuntimeError('must not run')\n", platform=mismatch)
    with td:
      result = materialize_artifacts(root, load_config(root))
      self.assertEqual(result.status, "INCOMPLETE")

  def test_verified_changes_can_be_committed_as_exact_set(self):
    body = "from pathlib import Path\nPath('dist').mkdir(exist_ok=True)\nPath('dist/bundle.js').write_text('x')\n"
    td, root, fx = self.make(body)
    with td:
      result = materialize_artifacts(root, load_config(root))
      before = fx.head()
      after = commit_artifact_changes(root, result, "artifact")
      self.assertNotEqual(before, after)
      changed = fx._run("diff-tree", "--no-commit-id", "--name-only", "-r", after).stdout.splitlines()
      self.assertEqual(changed, ["dist/bundle.js"])

  def test_generator_may_not_change_git_history(self):
    body = (
      "from pathlib import Path\n"
      "import subprocess\n"
      "Path('dist').mkdir(exist_ok=True)\n"
      "Path('dist/bundle.js').write_text('x')\n"
      "subprocess.run(['git','add','dist/bundle.js'], check=True)\n"
      "subprocess.run(['git','commit','-m','generator must not commit'], check=True)\n"
    )
    td, root, _ = self.make(body)
    with td:
      with self.assertRaisesRegex(ArtifactError, "Git history"):
        materialize_artifacts(root, load_config(root))

  def test_verifier_may_not_change_git_history(self):
    generator = (
      "from pathlib import Path\n"
      "Path('dist').mkdir(exist_ok=True)\n"
      "Path('dist/bundle.js').write_text('x')\n"
    )
    verifier = (
      "from pathlib import Path\n"
      "import subprocess\n"
      "Path('verification.txt').write_text('verified')\n"
      "subprocess.run(['git','add','verification.txt'], check=True)\n"
      "subprocess.run(['git','commit','-m','verifier must not commit'], check=True)\n"
    )
    td, root, _ = self.make(generator, verifier)
    with td:
      with self.assertRaisesRegex(ArtifactError, "verifier modified Git history"):
        materialize_artifacts(root, load_config(root))

  def test_generator_may_not_change_local_git_refs(self):
    body = (
      "from pathlib import Path\n"
      "import subprocess\n"
      "Path('dist').mkdir(exist_ok=True)\n"
      "Path('dist/bundle.js').write_text('x')\n"
      "subprocess.run(['git','tag','generator-side-effect'], check=True)\n"
    )
    td, root, _ = self.make(body)
    with td:
      with self.assertRaisesRegex(ArtifactError, "local Git refs"):
        materialize_artifacts(root, load_config(root))

  def test_verifier_may_not_change_local_git_refs(self):
    generator = (
      "from pathlib import Path\n"
      "Path('dist').mkdir(exist_ok=True)\n"
      "Path('dist/bundle.js').write_text('x')\n"
    )
    verifier = (
      "import subprocess\n"
      "subprocess.run(['git','tag','verifier-side-effect'], check=True)\n"
    )
    td, root, _ = self.make(generator, verifier)
    with td:
      with self.assertRaisesRegex(ArtifactError, "local Git refs"):
        materialize_artifacts(root, load_config(root))

  def test_generator_may_not_change_head_reference(self):
    body = (
      "from pathlib import Path\n"
      "import subprocess\n"
      "Path('dist').mkdir(exist_ok=True)\n"
      "Path('dist/bundle.js').write_text('x')\n"
      "subprocess.run(['git','switch','side'], check=True)\n"
    )
    td, root, fx = self.make(body)
    with td:
      fx._run("branch", "side")
      with self.assertRaisesRegex(ArtifactError, "HEAD reference"):
        materialize_artifacts(root, load_config(root))

  def test_dirty_worktree_is_rejected_before_generation(self):
    body = "from pathlib import Path\nPath('dist').mkdir(exist_ok=True)\nPath('dist/bundle.js').write_text('x')\n"
    td, root, _ = self.make(body)
    with td:
      (root / "dirty.txt").write_text("x")
      with self.assertRaisesRegex(ArtifactError, "clean worktree"):
        materialize_artifacts(root, load_config(root))


if __name__ == "__main__":
  unittest.main()
