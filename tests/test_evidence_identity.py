"""Specification-based evidence fingerprint verification for issue #68."""

import hashlib
import json
import unittest

from repo_workflow.evidence_identity import (
  SCHEMA, canonical_bytes, fingerprint, manifest,
)


def sha(data: bytes) -> str:
  return hashlib.sha256(data).hexdigest()


def valid():
  return manifest(
    "ART/a", source={"pkg/a.py": sha(b"a")},
    catalogue={".ci/tests.json": sha(b"catalogue")},
    configuration={".ci/repoworkflow.json": sha(b"config")},
    workflow={".github/workflows/ci.yml": sha(b"workflow")},
    capabilities={"python": "3.13", "os": "linux", "runner-api": "1"},
  )


class SpecificationTests(unittest.TestCase):
  def test_equivalent_maps_ignore_insertion_order(self):
    a = valid()
    b = dict(reversed(list(a.items())))
    b["capabilities"] = dict(reversed(list(a["capabilities"].items())))
    self.assertEqual(fingerprint(a), fingerprint(b))

  def test_repeated_fingerprint_is_deterministic(self):
    self.assertEqual(fingerprint(valid()), fingerprint(valid()))
    self.assertEqual(len(fingerprint(valid())), 64)

  def test_change_each_relevant_input_changes_identity(self):
    for section in ("source", "catalogue", "configuration", "workflow", "capabilities"):
      with self.subTest(section=section):
        candidate = valid()
        key = next(iter(candidate[section]))
        candidate[section][key] = "different" if section == "capabilities" else sha(b"changed")
        self.assertNotEqual(fingerprint(valid()), fingerprint(candidate))

  def test_change_unit_changes_identity(self):
    different = valid()
    different["unit"] = "ART/b"
    self.assertNotEqual(fingerprint(valid()), fingerprint(different))

  def test_unrelated_candidate_provenance_does_not_change_identity(self):
    # SHA, branch, provider, job and time are evidence provenance, not
    # semantic inputs unless a declared requirement makes them relevant.
    self.assertEqual(fingerprint(valid()), fingerprint(valid()))

  def test_missing_section_fails_closed(self):
    for section in ("source", "catalogue", "configuration", "workflow", "capabilities"):
      with self.subTest(section=section):
        item = valid()
        del item[section]
        with self.assertRaises(ValueError):
          fingerprint(item)

  def test_empty_section_fails_closed(self):
    for section in ("source", "catalogue", "configuration", "workflow", "capabilities"):
      with self.subTest(section=section):
        item = valid()
        item[section] = {}
        with self.assertRaises(ValueError):
          fingerprint(item)

  def test_unknown_fields_fail_closed(self):
    item = valid()
    item["provider"] = "github"
    with self.assertRaises(ValueError):
      fingerprint(item)

  def test_changed_schema_fails_closed(self):
    item = valid()
    item["schema"] = "future"
    with self.assertRaises(ValueError):
      fingerprint(item)

  def test_reject_bad_file_digests(self):
    for bad in ("", "abcd", "A" * 64, "g" * 64):
      with self.subTest(bad=bad):
        item = valid()
        item["source"]["pkg/a.py"] = bad
        with self.assertRaises(ValueError):
          fingerprint(item)

  def test_reject_invalid_names_and_capability_values(self):
    for bad in ("", " leading", "trailing ", "bad\\nkey", "e\\u0301"):
      with self.subTest(value=bad):
        item = valid()
        item["capabilities"] = {"runner": bad}
        with self.assertRaises(ValueError):
          fingerprint(item)

  def test_external_json_roundtrip(self):
    value = valid()
    parsed = json.loads(canonical_bytes(value))
    self.assertEqual(parsed, value)
    self.assertEqual(fingerprint(parsed), fingerprint(value))

  def test_schema_is_versioned(self):
    self.assertEqual(valid()["schema"], SCHEMA)


if __name__ == "__main__":
  unittest.main()
