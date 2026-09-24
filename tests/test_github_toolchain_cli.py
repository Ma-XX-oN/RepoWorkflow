import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]


class GithubToolchainCliTests(unittest.TestCase):
  def test_prepare_context_cli_reports_artifact_toolchain(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root, artifacts=[{
        "id": "bundle",
        "generatorCommand": [sys.executable, "scripts/generate.py"],
        "verifierCommand": [sys.executable, "scripts/verify.py"],
        "outputs": ["dist/bundle.js"],
        "committed": True,
        "capabilities": ["node-22"],
      }])
      completed = subprocess.run(
        [
          sys.executable,
          str(ROOT / "repo_workflow.py"),
          "--root",
          str(root),
          "github-prepare-context",
        ],
        check=True,
        capture_output=True,
        text=True,
      )
      self.assertEqual(json.loads(completed.stdout), {
        "runner": "ubuntu-latest",
        "nodeVersion": "22",
        "pythonVersion": "3.13",
      })


if __name__ == "__main__":
  unittest.main()
