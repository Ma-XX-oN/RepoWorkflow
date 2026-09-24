from pathlib import Path
import unittest

from repo_workflow.github_adapter import github_matrix, github_prepare_context


ROOT = Path(__file__).resolve().parents[1]


class DotnetToolchainProjectionTests(unittest.TestCase):
  def test_matrix_projects_dotnet_10_capability(self):
    config = {
      "environments": [{
        "id": "windows-dotnet10-python313",
        "required": True,
        "capabilities": ["dotnet-10", "python-3.13"],
      }]
    }
    github = {
      "schema": 1,
      "prepareRunner": "ubuntu-latest",
      "runners": {"windows-dotnet10-python313": "windows-latest"},
    }
    self.assertEqual(github_matrix(config, github), {
      "include": [{
        "id": "windows-dotnet10-python313",
        "runner": "windows-latest",
        "dotnetVersion": "10.0.x",
        "nodeVersion": "",
        "pythonVersion": "3.13",
      }]
    })

  def test_prepare_context_projects_dotnet_artifact_capability(self):
    config = {
      "artifacts": [{
        "id": "bundle",
        "capabilities": ["dotnet-10", "python-3.13"],
      }]
    }
    github = {"schema": 1, "prepareRunner": "windows-latest", "runners": {}}
    self.assertEqual(github_prepare_context(config, github), {
      "runner": "windows-latest",
      "dotnetVersion": "10.0.x",
      "nodeVersion": "",
      "pythonVersion": "3.13",
    })

  def test_canonical_adapter_provisions_dotnet_in_prepare_and_validate(self):
    workflow = (ROOT / "templates" / "github" / "ci.yml").read_text(encoding="utf-8")
    prepare = workflow.split("\n  prepare:\n", 1)[1].split("\n  validate:\n", 1)[0]
    validate = workflow.split("\n  validate:\n", 1)[1].split("\n  finalize:\n", 1)[0]

    self.assertIn("uses: actions/setup-dotnet@v4", prepare)
    self.assertIn(
      "if: fromJSON(needs.policy.outputs.prepare_context).dotnetVersion != ''",
      prepare,
    )
    self.assertIn(
      "dotnet-version: ${{ fromJSON(needs.policy.outputs.prepare_context).dotnetVersion }}",
      prepare,
    )

    self.assertIn("uses: actions/setup-dotnet@v4", validate)
    self.assertIn("if: matrix.dotnetVersion != ''", validate)
    self.assertIn("dotnet-version: ${{ matrix.dotnetVersion }}", validate)


if __name__ == "__main__":
  unittest.main()
