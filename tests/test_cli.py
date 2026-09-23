import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
  def test_matrix_uses_repository_configuration_without_exposing_commands(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)
      result = subprocess.run(
        [sys.executable, str(ROOT / "repo_workflow.py"), "--root", str(root), "matrix"],
        check=True, capture_output=True, text=True,
      )
      matrix = json.loads(result.stdout)
      self.assertEqual(matrix["include"][0]["id"], "local")
      self.assertNotIn("validationCommand", matrix["include"][0])

  def make_artifact_fixture(self, root: Path, generator_body: str, verifier_body: str):
    artifact = {
      "id": "bundle",
      "generatorCommand": [sys.executable, "scripts/generate.py"],
      "verifierCommand": [sys.executable, "scripts/verify.py"],
      "outputs": ["dist/bundle.js"],
      "committed": True,
    }
    fx = RepoFixture(root, artifacts=[artifact])
    (root / "scripts" / "generate.py").write_text(generator_body)
    (root / "scripts" / "verify.py").write_text(verifier_body)
    (root / ".ci" / "run-ci-request").write_text(fx.version + "\n\n")
    fx.commit("artifact scripts and request")
    fx.push()
    return fx

  def test_materialize_artifact_pass_result_uses_committed_candidate_sha(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = self.make_artifact_fixture(
        root,
        "from pathlib import Path\n"
        "Path('dist').mkdir(exist_ok=True)\n"
        "Path('dist/bundle.js').write_text('bundle')\n",
        "from pathlib import Path\n"
        "raise SystemExit(0 if Path('dist/bundle.js').read_text() == 'bundle' else 1)\n",
      )
      before = fx.head()
      result_path = root.parent / "artifact-result.json"
      completed = subprocess.run(
        [
          sys.executable, str(ROOT / "repo_workflow.py"), "--root", str(root),
          "materialize-artifacts", "--commit", "--result", str(result_path),
        ],
        capture_output=True, text=True,
      )
      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertNotEqual(fx.head(), before)
      value = json.loads(result_path.read_text())
      self.assertEqual(value["environment"], "__repoworkflow_artifacts__")
      self.assertEqual(value["status"], "PASS")
      self.assertEqual(value["commit"], fx.head())
      self.assertEqual(value["version"], fx.version)

  def test_materialize_artifact_policy_failure_writes_fail_result(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = self.make_artifact_fixture(
        root,
        "from pathlib import Path\nPath('undeclared.txt').write_text('x')\n",
        "raise SystemExit(0)\n",
      )
      result_path = root.parent / "artifact-result.json"
      completed = subprocess.run(
        [
          sys.executable, str(ROOT / "repo_workflow.py"), "--root", str(root),
          "materialize-artifacts", "--commit", "--result", str(result_path),
        ],
        capture_output=True, text=True,
      )
      self.assertEqual(completed.returncode, 1)
      value = json.loads(result_path.read_text())
      self.assertEqual(value["status"], "FAIL")
      self.assertEqual(value["commit"], fx.head())
      self.assertTrue(value["failures"])
      self.assertFalse((root / "undeclared.txt").exists())
      self.assertEqual(fx._run("status", "--porcelain").stdout, "")

  def test_materialize_artifact_history_mutation_is_failed_and_rolled_back(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = self.make_artifact_fixture(
        root,
        (
          "from pathlib import Path\n"
          "import subprocess\n"
          "Path('dist').mkdir(exist_ok=True)\n"
          "Path('dist/bundle.js').write_text('bundle')\n"
          "subprocess.run(['git','add','dist/bundle.js'], check=True)\n"
          "subprocess.run(['git','commit','-m','bad generator commit'], check=True)\n"
        ),
        "raise SystemExit(0)\n",
      )
      candidate = fx.head()
      result_path = root.parent / "artifact-result.json"
      completed = subprocess.run(
        [
          sys.executable, str(ROOT / "repo_workflow.py"), "--root", str(root),
          "materialize-artifacts", "--commit", "--result", str(result_path),
        ],
        capture_output=True, text=True,
      )
      self.assertEqual(completed.returncode, 1)
      self.assertEqual(fx.head(), candidate)
      self.assertEqual(fx._run("status", "--porcelain").stdout, "")
      value = json.loads(result_path.read_text())
      self.assertEqual(value["status"], "FAIL")
      self.assertEqual(value["commit"], candidate)

  def test_preflight_reports_candidate_identity(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      result = subprocess.run(
        [sys.executable, str(ROOT / "repo_workflow.py"), "--root", str(root), "preflight"],
        check=True, capture_output=True, text=True,
      )
      value = json.loads(result.stdout)
      self.assertEqual(value["version"], fx.version)
      self.assertEqual(value["commit"], fx.head())


if __name__ == "__main__":
  unittest.main()
