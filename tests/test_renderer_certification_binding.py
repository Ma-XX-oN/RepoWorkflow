from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / ".repoworkflow" / "renderer-certification.json"


def git_blob_sha(path: Path) -> str:
  data = path.read_bytes()
  header = f"blob {len(data)}\0".encode("ascii")
  return hashlib.sha1(header + data).hexdigest()


class RendererCertificationBindingTests(unittest.TestCase):
  def test_renderer_certification_matches_material_inputs(self):
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    self.assertEqual(value["schema_version"], 1)
    inputs = value["material_inputs"]
    self.assertTrue(inputs)

    actual = {
      path: git_blob_sha(ROOT / path)
      for path in inputs
    }
    self.assertEqual(actual, inputs)

  def test_certification_covers_canonical_graph_and_routing_pipeline(self):
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    paths = set(value["material_inputs"])
    required = {
      ".repoworkflow/tickets.csv",
      "repo_workflow/lane_decomposition.py",
      "repo_workflow/lane_graph_adapter.py",
      "repo_workflow/graph_render_model.py",
      "repo_workflow/graph_render.py",
      "repo_workflow/graph_render_types.py",
      "repo_workflow/graph_layout.py",
      "repo_workflow/graph_geometry.py",
      "repo_workflow/graph_route_semantics.py",
      "repo_workflow/graph_long_routes.py",
      "repo_workflow/graph_long_plan.py",
      "repo_workflow/graph_ordering.py",
      "repo_workflow/graph_boundary_plan.py",
      "repo_workflow/graph_boundary_order.py",
      "repo_workflow/graph_routing.py",
    }
    self.assertTrue(required <= paths)


if __name__ == "__main__":
  unittest.main()
