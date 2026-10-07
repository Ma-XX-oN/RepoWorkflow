from pathlib import Path
import json
import tempfile
import unittest

from repo_workflow.classification import (
  ClassificationError,
  classify_paths,
  load_change_classes,
)


class ClassificationTests(unittest.TestCase):
  def policy(self):
    return {
      "docs": {
        "paths": ["**/*.md", "docs/**", ".gitignore", "VERSION"],
        "validation": "fast",
      }
    }

  def test_docs_and_version_are_docs_class(self):
    self.assertEqual(
      classify_paths(["DESIGN.md", "VERSION"], self.policy()),
      ("docs", "fast"),
    )

  def test_source_change_forces_full_validation(self):
    self.assertEqual(
      classify_paths(["DESIGN.md", "repo_workflow.py", "VERSION"], self.policy()),
      (None, "full"),
    )

  def test_nested_markdown_matches_recursive_pattern(self):
    self.assertEqual(
      classify_paths(["docs/design/notes.md"], self.policy()),
      ("docs", "fast"),
    )

  def test_empty_diff_does_not_claim_a_class(self):
    self.assertEqual(classify_paths([], self.policy()), (None, "full"))

  def test_policy_rejects_unknown_fields(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      path = root / ".repoworkflow"
      path.mkdir()
      (path / "change-classes.json").write_text(json.dumps({
        "schema": 1,
        "classes": {
          "docs": {
            "paths": ["**/*.md"],
            "validation": "fast",
            "trustCommitMessage": True,
          }
        },
      }))
      with self.assertRaises(ClassificationError):
        load_change_classes(root)


if __name__ == "__main__":
  unittest.main()
