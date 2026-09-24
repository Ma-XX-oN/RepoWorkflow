from pathlib import Path
import unittest

import repo_workflow.github_adapter as adapter


ROOT = Path(__file__).resolve().parents[1]


class GithubToolchainTests(unittest.TestCase):
  def test_matrix_projects_declared_node_and_python_versions(self):
    config = {"environments": [{
      "id": "linux",
      "required": True,
      "capabilities": ["node-22", "python-3.13"],
    }]}
    github = {
      "schema": 1,
      "prepareRunner": "ubuntu-latest",
      "runners": {"linux": "ubuntu-latest"},
    }
    self.assertEqual(adapter.github_matrix(config, github), {"include": [{
      "id": "linux",
      "runner": "ubuntu-latest",
      "nodeVersion": "22",
      "pythonVersion": "3.13",
    }]})

  def test_matrix_rejects_conflicting_node_versions(self):
    config = {"environments": [{
      "id": "linux",
      "required": True,
      "capabilities": ["node-20", "node-22"],
    }]}
    github = {
      "schema": 1,
      "prepareRunner": "ubuntu-latest",
      "runners": {"linux": "ubuntu-latest"},
    }
    with self.assertRaises(adapter.AdapterError):
      adapter.github_matrix(config, github)

  def test_prepare_context_projects_artifact_toolchains(self):
    context_fn = getattr(adapter, "github_prepare_context", None)
    self.assertIsNotNone(context_fn, "GitHub adapter lacks artifact prepare context")
    config = {"artifacts": [{
      "id": "bundle",
      "capabilities": ["node-22"],
    }]}
    github = {
      "schema": 1,
      "prepareRunner": "ubuntu-latest",
      "runners": {},
    }
    self.assertEqual(context_fn(config, github), {
      "runner": "ubuntu-latest",
      "nodeVersion": "22",
      "pythonVersion": "3.13",
    })

  def test_canonical_template_consumes_projected_toolchains(self):
    text = (ROOT / "templates" / "github" / "ci.yml").read_text(encoding="utf-8")
    self.assertGreaterEqual(text.count("uses: actions/setup-node@v4"), 2)
    self.assertIn("matrix.nodeVersion", text)
    self.assertIn("prepare_context", text)
    self.assertIn("nodeVersion", text)


if __name__ == "__main__":
  unittest.main()
