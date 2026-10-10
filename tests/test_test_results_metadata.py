"""Black-box rejection of malformed testing-results identity metadata."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "repo_workflow.py"


class ResultsMetadataTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    subprocess.run(
      ["git", "-C", str(self.root), "init", "-qb", "issue-545-meta"],
      check=True, capture_output=True,
    )
    for key, value in (
      ("user.name", "Fixture"),
      ("user.email", "fixture@example.invalid"),
    ):
      subprocess.run(
        ["git", "-C", str(self.root), "config", key, value],
        check=True, capture_output=True,
      )
    (self.root / "README").write_text("fixture\\n")
    subprocess.run(
      ["git", "-C", str(self.root), "add", "README"],
      check=True, capture_output=True,
    )
    subprocess.run(
      ["git", "-C", str(self.root), "commit", "-qm", "initial"],
      check=True, capture_output=True,
    )
    self.log = (
      self.root / ".repoworkflow/validation/testResults-545.jsonl"
    )
    self.log.parent.mkdir(parents=True)
    self.valid = {
      "testSHA": "a" * 40,
      "kind": "GREEN",
      "result": "succeeded",
      "runner": "local",
    }

  def result(self, records):
    self.log.write_text(
      "".join(json.dumps(record) + "\n" for record in records)
    )
    return subprocess.run(
      [sys.executable, str(CLI), "--root", str(self.root),
       "test", "results"],
      text=True, capture_output=True, check=False,
    )

  def test_valid_minimal_record_preserved(self):
    output = self.result([self.valid])
    self.assertEqual(output.returncode, 0, output.stderr)
    self.assertEqual(json.loads(output.stdout), self.valid)

  def test_invalid_identity_and_metadata_refused_before_output(self):
    malformed = (
      {"testSHA": 123},
      {"testSHA": True},
      {"testSHA": "a" * 39},
      {"testSHA": "g" * 40},
      {"kind": []},
      {"kind": ""},
      {"result": False},
      {"result": ""},
      {"runner": {}},
      {"runner": ""},
    )
    for mutation in malformed:
      with self.subTest(mutation=mutation):
        candidate = dict(self.valid, **mutation)
        output = self.result([self.valid, candidate])
        self.assertEqual(output.returncode, 2)
        self.assertEqual(output.stdout, "")
        self.assertIn("invalid testing log metadata", output.stderr)


  def test_group_observation_cardinality_and_shape(self):
    valid_group = {"group": "issue-545-one", "exit_code": 0}
    for groups in (
      [],
      [valid_group],
      [valid_group, {"group": "issue-545-two", "exit_code": 1}],
    ):
      with self.subTest(valid=groups):
        record = dict(self.valid, groups=groups)
        output = self.result([record])
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertEqual(json.loads(output.stdout), record)

    malformed_groups = (
      None,
      {},
      "issue-545-one",
      [1],
      [{}],
      [{"group": "", "exit_code": 0}],
      [{"group": "issue-545-one"}],
      [{"group": "issue-545-one", "exit_code": False}],
      [{"group": "issue-545-one", "exit_code": "0"}],
      [valid_group, dict(valid_group)],
    )
    for groups in malformed_groups:
      with self.subTest(invalid=groups):
        output = self.result([
          self.valid, dict(self.valid, groups=groups),
        ])
        self.assertEqual(output.returncode, 2)
        self.assertEqual(output.stdout, "")
        self.assertIn("invalid testing log groups", output.stderr)


if __name__ == "__main__":
  unittest.main()
