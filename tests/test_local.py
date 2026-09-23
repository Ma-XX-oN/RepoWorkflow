from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

from repo_workflow.actions_policy import ActionsPolicyError
from repo_workflow.local import verify_local
from tests.support import RepoFixture


CANONICAL_URL = "https://github.com/Ma-XX-oN/RepoWorkflow.git"


class LocalVerifyTests(unittest.TestCase):
  def git(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
      ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )

  def make_consumer(self, *, validation_body="raise SystemExit(0)\n", platform="any"):
    td = tempfile.TemporaryDirectory()
    base = Path(td.name)
    root = base / "repo"
    root.mkdir()
    fx = RepoFixture(root, validation_body=validation_body, platform=platform)

    engine_source = base / "engine-source"
    engine_remote = base / "engine.git"
    engine_source.mkdir()
    self.git(engine_source, "init", "-b", "main")
    self.git(engine_source, "config", "user.name", "Test")
    self.git(engine_source, "config", "user.email", "test@example.invalid")
    (engine_source / "templates" / "github").mkdir(parents=True)
    canonical = "name: CI\n"
    (engine_source / "templates" / "github" / "ci.yml").write_text(canonical)
    self.git(engine_source, "add", ".")
    self.git(engine_source, "commit", "-m", "engine")
    subprocess.run(
      ["git", "init", "--bare", str(engine_remote)],
      check=True, capture_output=True,
    )
    self.git(engine_source, "remote", "add", "origin", str(engine_remote))
    self.git(engine_source, "push", "-u", "origin", "main")
    subprocess.run(
      ["git", "--git-dir", str(engine_remote), "symbolic-ref", "HEAD", "refs/heads/main"],
      check=True, capture_output=True,
    )

    subprocess.run(
      ["git", "-c", "protocol.file.allow=always", "submodule", "add",
       str(engine_remote), "RepoWorkflow"],
      cwd=root, check=True, capture_output=True,
    )
    self.git(
      root, "config", "-f", ".gitmodules", "submodule.RepoWorkflow.url",
      CANONICAL_URL,
    )
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "ci.yml").write_text(canonical)
    # Rebind the request to this complete consumer candidate.
    (root / ".ci" / "run-ci-request").write_text(fx.version + "\n\n")
    fx.commit("adopt RepoWorkflow")
    fx.push()
    return td, root, fx

  def test_local_verify_uses_same_guard_policy_and_result_semantics(self):
    td, root, _ = self.make_consumer()
    with td:
      self.assertEqual(
        verify_local(root, engine_root=root / "RepoWorkflow"),
        "PASS",
      )

  def test_local_verify_enforces_canonical_github_adapter(self):
    td, root, fx = self.make_consumer()
    with td:
      (root / ".github" / "workflows" / "ci.yml").write_text("name: changed\n")
      (root / ".ci" / "run-ci-request").write_text(fx.version + "\n\n\n")
      fx.commit("break adapter and refresh request")
      fx.push()
      with self.assertRaises(ActionsPolicyError):
        verify_local(root, engine_root=root / "RepoWorkflow")

  def add_artifact(
    self, root: Path, fx: RepoFixture, *, generator_body: str, verifier_body: str
  ) -> None:
    config_path = root / ".ci" / "repoworkflow.json"
    config = json.loads(config_path.read_text())
    config["artifacts"] = [{
      "id": "bundle",
      "generatorCommand": [sys.executable, "scripts/generate.py"],
      "verifierCommand": [sys.executable, "scripts/verify.py"],
      "outputs": ["dist/bundle.js"],
      "committed": True,
    }]
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    (root / "scripts" / "generate.py").write_text(generator_body)
    (root / "scripts" / "verify.py").write_text(verifier_body)
    (root / ".ci" / "run-ci-request").write_text(fx.version + "\n\n\n")
    fx.commit("declare generated artifact and refresh request")
    fx.push()

  def test_local_verify_materializes_commits_and_validates_artifact_candidate(self):
    td, root, fx = self.make_consumer()
    with td:
      self.add_artifact(
        root, fx,
        generator_body=(
          "from pathlib import Path\n"
          "Path('dist').mkdir(exist_ok=True)\n"
          "Path('dist/bundle.js').write_text('bundle')\n"
        ),
        verifier_body=(
          "from pathlib import Path\n"
          "raise SystemExit(0 if Path('dist/bundle.js').read_text() == 'bundle' else 1)\n"
        ),
      )
      before = fx.head()
      outcome = verify_local(root, engine_root=root / "RepoWorkflow")
      self.assertEqual(outcome, "PASS")
      self.assertNotEqual(fx.head(), before)
      changed = fx._run(
        "diff-tree", "--no-commit-id", "--name-only", "-r", fx.head()
      ).stdout.splitlines()
      self.assertEqual(changed, ["dist/bundle.js"])
      self.assertEqual(fx._run("status", "--porcelain").stdout, "")

  def test_local_verify_artifact_failure_is_aggregated_and_side_effects_are_rolled_back(self):
    td, root, fx = self.make_consumer()
    with td:
      self.add_artifact(
        root, fx,
        generator_body=(
          "from pathlib import Path\n"
          "Path('undeclared.txt').write_text('x')\n"
        ),
        verifier_body="raise SystemExit(0)\n",
      )
      candidate = fx.head()
      outcome = verify_local(root, engine_root=root / "RepoWorkflow")
      self.assertEqual(outcome, "FAIL")
      self.assertEqual(fx.head(), candidate)
      self.assertFalse((root / "undeclared.txt").exists())
      self.assertEqual(fx._run("status", "--porcelain").stdout, "")

  def test_platform_mismatch_is_incomplete(self):
    mismatch = "windows" if not sys.platform.startswith("win") else "linux"
    td, root, _ = self.make_consumer(
      validation_body="raise RuntimeError('must not run')\n", platform=mismatch
    )
    with td:
      self.assertEqual(
        verify_local(root, engine_root=root / "RepoWorkflow"),
        "INCOMPLETE",
      )


if __name__ == "__main__":
  unittest.main()
