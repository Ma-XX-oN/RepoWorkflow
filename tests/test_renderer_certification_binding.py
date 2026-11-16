from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.git import git_bytes, git_checkout_bytes


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / ".repoworkflow" / "renderer-certification.json"


def git_blob_sha(path: Path, *, root: Path = ROOT) -> str:
  relative = path.relative_to(root).as_posix()
  data = git_bytes(root, "show", "HEAD:" + relative).stdout
  checkout = git_checkout_bytes(root, relative)
  if checkout is None or path.is_symlink() or path.read_bytes() != checkout:
    raise AssertionError("certified source does not match Git-materialized checkout")
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
      *{
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "repo_workflow").glob("graph_*.py")
      },
    }
    self.assertTrue(required <= paths)


  def test_committed_blob_hash_survives_checkout_eol_conversion(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.name", "Fixture"),
        ("config", "user.email", "fixture@example.invalid"),
        ("config", "core.autocrlf", "true"),
      ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
      path = root / "graph_test.py"
      path.write_bytes(b"line1\nline2\n")
      subprocess.run(["git", "add", "graph_test.py"], cwd=root,
                     check=True, capture_output=True)
      subprocess.run(["git", "commit", "-qm", "source"], cwd=root,
                     check=True, capture_output=True)
      raw = git_bytes(root, "show", "HEAD:graph_test.py").stdout
      materialized = git_checkout_bytes(root, "graph_test.py")
      self.assertIsNotNone(materialized)
      path.write_bytes(materialized)
      header = f"blob {len(raw)}\0".encode("ascii")
      self.assertEqual(git_blob_sha(path, root=root),
                       hashlib.sha1(header + raw).hexdigest())
      path.write_bytes(materialized + b"tamper")
      with self.assertRaisesRegex(AssertionError, "Git-materialized checkout"):
        git_blob_sha(path, root=root)


if __name__ == "__main__":
  unittest.main()
