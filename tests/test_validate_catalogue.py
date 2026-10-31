"""Regression test inventory is exclusively catalogue-derived and complete."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.validate import catalogued_modules, _unique_tests


class CatalogueRegressionTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    (self.root / ".ci").mkdir()
    (self.root / "tests").mkdir()
    (self.root / "tests/test_one.py").write_text(
      "import unittest\nclass One(unittest.TestCase):\n"
      "  def test_ok(self): pass\n", encoding="utf-8")
    self.catalogue = {
      "test-harnesses": {
        "unittest": {"command": "python", "layout": ["-m", "unittest", "$test"]}
      },
      "tests": [{
        "test-harness": "unittest",
        "regression-one": {"type": "regression", "name": "tests.test_one"}
      }]
    }
    self.save()

  def save(self):
    (self.root / ".ci/tests.json").write_text(
      json.dumps(self.catalogue), encoding="utf-8")

  def test_catalogue_is_exact_inventory(self):
    self.assertEqual(catalogued_modules(self.root), ("tests.test_one",))

  def test_unregistered_file_fails_closed(self):
    (self.root / "tests/test_two.py").write_text("", encoding="utf-8")
    with self.assertRaisesRegex(ValueError, "unregistered"):
      catalogued_modules(self.root)

  def test_missing_registered_file_fails_closed(self):
    (self.root / "tests/test_one.py").unlink()
    with self.assertRaisesRegex(ValueError, "missing source"):
      catalogued_modules(self.root)

  def test_duplicate_group_alias_does_not_duplicate_execution(self):
    self.catalogue["tests"][0]["regression-alias"] = {
      "type": "regression", "name": "tests.test_one"
    }
    self.save()
    self.assertEqual(catalogued_modules(self.root), ("tests.test_one",))

  def test_duplicate_imported_testcase_identity_executes_once(self):
    class Example(unittest.TestCase):
      def test_ok(self):
        pass
    test = Example("test_ok")
    source = unittest.TestSuite([test, Example("test_ok")])
    reduced = _unique_tests(source)
    self.assertEqual(reduced.countTestCases(), 1)


if __name__ == "__main__":
  unittest.main()
