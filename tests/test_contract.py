from pathlib import Path
import sys
import tempfile
import unittest

from repo_workflow.config import load_config
from repo_workflow.guard import GuardError, validate_candidate
from tests.support import RepoFixture


class GuardTests(unittest.TestCase):
  def make(self, **kwargs):
    td = tempfile.TemporaryDirectory()
    root = Path(td.name) / "repo"
    root.mkdir()
    fixture = RepoFixture(root, **kwargs)
    return td, root, fixture

  def test_matching_request_version_and_untagged_candidate_passes(self):
    td, root, fx = self.make()
    with td:
      candidate = validate_candidate(root, load_config(root))
      self.assertEqual(candidate.version, fx.version)
      self.assertEqual(candidate.commit, fx.head())

  def test_request_version_mismatch_is_rejected(self):
    td, root, fx = self.make()
    with td:
      (root / ".ci" / "run-ci-request").write_text("1.0.0-issue.1.2\n")
      fx.commit("wrong request")
      fx.push()
      with self.assertRaisesRegex(GuardError, "does not match"):
        validate_candidate(root, load_config(root))

  def test_expected_sha_mismatch_is_rejected(self):
    td, root, fx = self.make()
    with td:
      with self.assertRaisesRegex(GuardError, "does not match expected"):
        validate_candidate(root, load_config(root), expected_sha="0" * 40)

  def test_success_terminal_tag_on_authoritative_remote_is_rejected(self):
    td, root, fx = self.make()
    with td:
      fx.tag_remote(f"v{fx.version}")
      with self.assertRaisesRegex(GuardError, "terminal result tag"):
        validate_candidate(root, load_config(root))

  def test_failure_terminal_tag_on_authoritative_remote_is_rejected(self):
    td, root, fx = self.make()
    with td:
      fx.tag_remote(f"v{fx.version}-CI-FAIL")
      with self.assertRaisesRegex(GuardError, "terminal result tag"):
        validate_candidate(root, load_config(root))

  def test_stale_local_terminal_tag_absent_from_remote_does_not_block(self):
    td, root, fx = self.make()
    with td:
      fx._run("tag", f"v{fx.version}")
      candidate = validate_candidate(root, load_config(root))
      self.assertEqual(candidate.commit, fx.head())

  def test_source_change_after_request_is_rejected(self):
    td, root, fx = self.make()
    with td:
      (root / "source.txt").write_text("later\n")
      fx.commit("later source")
      fx.push()
      with self.assertRaisesRegex(GuardError, "after the CI request"):
        validate_candidate(root, load_config(root))

  def test_declared_artifact_change_after_request_is_allowed(self):
    artifact = {
      "id": "bundle",
      "generatorCommand": [sys.executable, "scripts/generate.py"],
      "verifierCommand": [sys.executable, "scripts/verify.py"],
      "outputs": ["dist/bundle.js"],
      "committed": True,
    }
    td, root, fx = self.make(artifacts=[artifact])
    with td:
      (root / "dist").mkdir()
      (root / "dist" / "bundle.js").write_text("generated\n")
      fx.commit("generated artifact")
      fx.push()
      candidate = validate_candidate(root, load_config(root))
      self.assertEqual(candidate.commit, fx.head())

  def test_dirty_checkout_is_rejected(self):
    td, root, fx = self.make()
    with td:
      (root / "dirty.txt").write_text("dirty\n")
      with self.assertRaisesRegex(GuardError, "not clean"):
        validate_candidate(root, load_config(root))

  def test_version_command_that_mutates_local_refs_is_rejected(self):
    td, root, fx = self.make()
    with td:
      (root / "scripts" / "version.py").write_text(
        "from pathlib import Path\n"
        "import subprocess\n"
        "subprocess.run(['git','tag','version-side-effect'], check=True)\n"
        "print((Path(__file__).resolve().parents[1] / 'VERSION').read_text().strip())\n"
      )
      (root / ".ci" / "run-ci-request").write_text(fx.version + "\n\n")
      fx.commit("ref-mutating version command and request")
      fx.push()
      with self.assertRaisesRegex(GuardError, "local Git refs"):
        validate_candidate(root, load_config(root))

  def test_version_command_that_changes_head_reference_is_rejected(self):
    td, root, fx = self.make()
    with td:
      (root / "scripts" / "version.py").write_text(
        "from pathlib import Path\n"
        "import subprocess\n"
        "subprocess.run(['git','switch','side'], check=True)\n"
        "print((Path(__file__).resolve().parents[1] / 'VERSION').read_text().strip())\n"
      )
      (root / ".ci" / "run-ci-request").write_text(fx.version + "\n\n")
      fx.commit("head-switching version command and request")
      fx.push()
      fx._run("branch", "side")
      with self.assertRaisesRegex(GuardError, "HEAD reference"):
        validate_candidate(root, load_config(root))

  def test_version_command_that_mutates_worktree_is_rejected(self):
    td, root, fx = self.make()
    with td:
      (root / "scripts" / "version.py").write_text(
        "from pathlib import Path\n"
        "root=Path(__file__).resolve().parents[1]\n"
        "(root/'mutated.txt').write_text('x')\n"
        "print((root/'VERSION').read_text().strip())\n"
      )
      fx.commit("mutating version command")
      fx.push()
      with self.assertRaises(GuardError):
        validate_candidate(root, load_config(root))


if __name__ == "__main__":
  unittest.main()
