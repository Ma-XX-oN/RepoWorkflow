"""Specification-derived zero/one/many/invalid CLI acceptance on real Git."""
import json
import unittest

from tests import test_issue629_stage_cardinality as source


class ExpandedStageCardinality(source.LocalStageCardinalityTests):
  """Includes unchanged #629 cardinalities plus remaining stage negatives."""

  def test_no_red_selection_local_and_remote_never_requests(self):
    self.catalogue(["issue-629-one"])
    original = self.git("rev-parse", "HEAD")
    for args in (("RED",), ("RED", "--remote")):
      with self.subTest(args=args):
        result = self.cli("test", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Hosted request", result.stdout)
        self.assertEqual(self.log()[-1]["result"], "SKIPPED")
        self.assertEqual(self.git("rev-parse", "HEAD"), original)
        self.assertFalse((self.root / ".ci/run").exists())

  def test_no_green_selection_local_and_remote_never_requests(self):
    self.catalogue(["issue-629-one"])
    original = self.git("rev-parse", "HEAD")
    for args in (("GREEN",), ("GREEN", "--remote")):
      with self.subTest(args=args):
        result = self.cli("test", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log()[-1]["result"], "SKIPPED")
        self.assertEqual(self.git("rev-parse", "HEAD"), original)
        self.assertFalse((self.root / ".ci/run").exists())

  def test_red_unknown_group_cannot_select(self):
    self.catalogue(["issue-629-good"])
    status = self.cli("test", "RED", "issue-629-unregistered")
    self.assertNotEqual(status.returncode, 0)
    self.assertFalse((self.root / ".ci/red-green.txt").exists())

  def test_red_two_line_selection_fails_closed(self):
    self.catalogue(["issue-629-good"])
    selected = self.root / ".ci/red-green.txt"
    selected.write_text("issue-629-good\nissue-629-other\n")
    self.git("add", ".ci/red-green.txt")
    self.git("commit", "-m", "malformed committed RED selection")
    status = self.cli("test", "RED")
    self.assertNotEqual(status.returncode, 0)
    self.assertFalse(any(r.get("result") == "succeeded" for r in self.log()))

  def test_multiple_explicit_red_groups_are_invalid(self):
    self.catalogue(["issue-629-one", "issue-629-two"])
    status = self.cli("test", "RED", "issue-629-one", "issue-629-two")
    self.assertNotEqual(status.returncode, 0)
    self.assertFalse((self.root / ".ci/red-green.txt").exists())

  def test_all_nonred_stages_reject_explicit_group_arity(self):
    self.catalogue(["issue-629-one"], temporary=True)
    for stage in ("GREEN", "temporary", "regression",
                  "integration", "results"):
      with self.subTest(stage=stage):
        result = self.cli("test", stage, "issue-629-one")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(r.get("result") == "succeeded" for r in self.log()))

  def test_duplicate_temporary_test_keys_rejected(self):
    manifest = self.catalogue(["issue-629-one"], temporary=True)
    value = json.loads(manifest.read_text())
    value["tests"].append({
      "test-harness": "unittest",
      "issue-629-one": {"type": "regression", "name": "smoke_case"},
    })
    manifest.write_text(json.dumps(value))
    result = self.cli("test", "temporary")
    self.assertNotEqual(result.returncode, 0)
    self.assertFalse(any(r.get("result") == "succeeded" for r in self.log()))

  def test_many_temporary_groups_fail_without_reusable_pass(self):
    self.catalogue(["issue-629-a", "issue-629-b"], temporary=True)
    test = self.root / "smoke_case.py"
    test.write_text(test.read_text().replace(
      "self.assertTrue(True)", 'self.fail("EXPECTED_FAIL")'))
    self.git("add", "smoke_case.py")
    self.git("commit", "-m", "expected failure")
    result = self.cli("test", "temporary")
    self.assertNotEqual(result.returncode, 0)
    record = self.log()[-1]
    self.assertEqual(record["result"], "failed")
    self.assertFalse(record["reusable"])
    self.assertEqual(len(record["groups"]), 2)
    self.assertTrue(all(x["exit_code"] != 0 for x in record["groups"]))

  def test_many_results_are_read_back_without_partial_fabrication(self):
    from pathlib import Path
    path = self.root / ".repoworkflow/validation/testResults-629.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
      {"testSHA": self.candidate, "kind": "RED", "result": "INCOMPLETE",
       "runner": "local"},
      {"testSHA": self.candidate, "kind": "GREEN", "result": "succeeded",
       "runner": "local"},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    result = self.cli("test", "results")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual([json.loads(x) for x in result.stdout.splitlines()], rows)


if __name__ == "__main__":
  unittest.main()
