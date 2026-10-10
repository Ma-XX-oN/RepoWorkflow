"""Independent, fail-closed #629 preparatory acceptance matrix checks."""

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "tests" / "fixtures" / "issue629_matrix.json"
EXPECTED = {f"M{i:02d}" for i in range(1, 13)}
PROVIDER = {"provider", "integration"}


def evaluate(entries, observations):
  """Return accepted IDs only when authoritative evidence was supplied."""
  accepted = set()
  for entry in entries:
    item = observations.get(entry["id"])
    if not isinstance(item, dict):
      continue
    if item.get("result") != "succeeded":
      continue
    if entry["environment"] in PROVIDER:
      if not item.get("provider_verified"):
        continue
      if not item.get("candidate_sha") or not item.get("evidence_id"):
        continue
      if item.get("candidate_sha") != item.get("tested_sha"):
        continue
    else:
      if not item.get("executed") or not item.get("test_revision"):
        continue
    accepted.add(entry["id"])
  return accepted


class IndependentMatrixTests(unittest.TestCase):
  def setUp(self):
    self.entries = json.loads(MATRIX.read_text(encoding="utf-8"))["entries"]

  def test_unique_complete_requirement_trace(self):
    self.assertEqual({row["id"] for row in self.entries}, EXPECTED)
    self.assertEqual(len(self.entries), len(EXPECTED))
    for row in self.entries:
      self.assertTrue(row["requirement"])
      self.assertTrue(row["test"].startswith("test_"))
      self.assertIn(row["environment"], {"CLI", "provider", "integration"})
      self.assertEqual(row["status"], "pending")
      self.assertIsNone(row["evidence"])

  def test_unobserved_cases_are_never_green(self):
    self.assertEqual(evaluate(self.entries, {}), set())

  def test_fabricated_provider_pass_is_not_accepted(self):
    provider = next(x for x in self.entries if x["environment"] == "provider")
    fake = {provider["id"]: {"result": "succeeded", "executed": True}}
    self.assertEqual(evaluate(self.entries, fake), set())

  def test_provider_candidate_mismatch_is_rejected(self):
    provider = next(x for x in self.entries if x["environment"] == "provider")
    observation = {"result": "succeeded", "provider_verified": True,
                   "candidate_sha": "a" * 40, "tested_sha": "b" * 40,
                   "evidence_id": "provider-run-1"}
    self.assertEqual(evaluate(self.entries, {provider["id"]: observation}), set())

  def test_failed_incomplete_and_replayed_without_identity_rejected(self):
    provider = next(x for x in self.entries if x["environment"] == "provider")
    for outcome in ("failed", "incomplete", None):
      with self.subTest(outcome=outcome):
        observation = {"result": outcome, "provider_verified": True,
                       "candidate_sha": "a" * 40, "tested_sha": "a" * 40,
                       "evidence_id": "provider-run-1"}
        self.assertEqual(
          evaluate(self.entries, {provider["id"]: observation}), set())
    replay = {"result": "succeeded", "provider_verified": True,
              "candidate_sha": "a" * 40, "tested_sha": "b" * 40,
              "evidence_id": "provider-run-1"}
    self.assertEqual(evaluate(self.entries, {provider["id"]: replay}), set())

  def test_verified_provider_observation_requires_complete_identity(self):
    provider = next(x for x in self.entries if x["environment"] == "provider")
    observation = {"result": "succeeded", "provider_verified": True,
                   "candidate_sha": "a" * 40, "tested_sha": "a" * 40,
                   "evidence_id": "provider-run-1"}
    self.assertEqual(
      evaluate(self.entries, {provider["id"]: observation}), {provider["id"]})

  def test_cli_requires_execution_and_test_revision(self):
    cli = next(x for x in self.entries if x["environment"] == "CLI")
    self.assertEqual(evaluate(self.entries, {cli["id"]: {
      "result": "succeeded", "executed": True}}), set())
    self.assertEqual(evaluate(self.entries, {cli["id"]: {
      "result": "succeeded", "executed": True, "test_revision": "abc"}}),
      {cli["id"]})


if __name__ == "__main__":
  unittest.main()
