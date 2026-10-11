"""Provider-backed parity between committed selections and immutable outcomes."""
from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from repo_workflow.github_artifact import _artifact_bytes
from repo_workflow.github_evidence import github_json
from repo_workflow.test_catalogue import load_test_catalogue

REPO = "Ma-XX-oN/RepoWorkflow"
API = "https://api.github.com/repos/" + REPO
SOURCE = "2c4dacb52f94f0f8c3decc9ad2b768953a4e074d"
STAGES = (
  ("RED", 38116126460,
   "e720c95f36308d47c83568dce3e3b41788e76797",
   ".ci/red-green.txt"),
  ("temporary", 38116026636,
   "ca2ed45abf602a117cc4a89269cadfc9b6205a30",
   ".ci/temp-tests.json"),
  ("GREEN", 38115919788, SOURCE, ".ci/red-green.txt"),
  ("regression", 38115863747, SOURCE, None),
  ("integration", 38115856141, SOURCE, None),
)


def file_bytes(ref, path):
  item = github_json(API + "/contents/" + path + "?ref=" + ref)
  assert item.get("encoding") == "base64"
  return base64.b64decode(item["content"].replace("\n", ""))


def result_from_immutable(run):
  items = github_json(API + "/actions/runs/" + str(run) + "/artifacts?per_page=100")
  matches = [x for x in items["artifacts"]
             if x.get("name") == "provider-result-" + str(run)
             and not x.get("expired")]
  assert len(matches) == 1, "exactly one unexpired immutable artifact"
  data = _artifact_bytes(API + "/actions/artifacts/" + str(matches[0]["id"]) + "/zip")
  with ZipFile(BytesIO(data)) as z:
    return next(row for row in
      (json.loads(line) for line in z.read("testResults-543.jsonl").decode().splitlines())
      if row.get("providerRunId") == run)


class LiveLocalHostedParity(unittest.TestCase):
  def check(self, index):
    stage, run, ref, manifest = STAGES[index]
    record = result_from_immutable(run)
    self.assertEqual(record["testSHA"], ref)
    self.assertEqual(record["providerCandidateSHA"], ref)
    self.assertEqual(record["kind"], stage)
    self.assertEqual(record["result"], "succeeded")
    if stage in ("RED", "GREEN"):
      selected = file_bytes(ref, manifest).decode("utf-8").splitlines()
      self.assertEqual(len(selected), 1)
      with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".ci").mkdir()
        (root / ".ci/tests.json").write_bytes(file_bytes(ref, ".ci/tests.json"))
        self.assertIn(selected[0], load_test_catalogue(root).groups)
      self.assertEqual([g["group"] for g in record["groups"]], selected)
    elif stage == "temporary":
      with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".ci").mkdir()
        (root / ".ci/temp-tests.json").write_bytes(file_bytes(ref, manifest))
        expected = sorted(load_test_catalogue(
          root, catalogue_path=Path(".ci/temp-tests.json")).groups)
      self.assertEqual(sorted(g["group"] for g in record["groups"]), expected)
    elif stage == "integration":
      self.assertEqual(
        sorted(g["group"] for g in record["groups"]),
        sorted(("regression", "argv-limits",
                "graph-renderer-platform", "ticket-merge-platform")),
      )
    else:
      self.assertFalse(record.get("groups"), "regression is an aggregate stage")

  def test_red_committed_selection_parity(self):
    self.check(0)

  def test_temporary_many_group_parity(self):
    self.check(1)

  def test_green_committed_selection_parity(self):
    self.check(2)

  def test_regression_aggregate_parity(self):
    self.check(3)

  def test_integration_aggregate_and_platform_group_parity(self):
    self.check(4)


if __name__ == "__main__":
  unittest.main()
