from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.classification import (
  ClassificationError,
  classify_paths,
  load_change_classes,
  changed_paths,
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


  def test_backslash_is_not_a_path_separator_in_git_identity(self):
    literal = r"literal\backslash.md"
    only_slash = {
      "docs": {"paths": ["literal/backslash.md"], "validation": "fast"},
    }
    self.assertEqual(classify_paths([literal], only_slash), (None, "full"))
    if os.name != "nt":
      with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for cmd in (
          ("init", "-q", "-b", "main"),
          ("config", "user.name", "Fixture"),
          ("config", "user.email", "fixture@example.invalid"),
          ("commit", "-qm", "base", "--allow-empty"),
        ):
          subprocess.run(["git", *cmd], cwd=root,
                         check=True, capture_output=True)
        base = subprocess.check_output(
          ["git", "rev-parse", "HEAD"], cwd=root,
        ).decode("ascii").strip()
        (root / literal).write_text("literal backslash name\n", encoding="utf-8")
        subprocess.run(["git", "add", "--", literal], cwd=root,
                       check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "add literal name"], cwd=root,
                       check=True, capture_output=True)
        self.assertEqual(changed_paths(root, base), [literal])

  def test_invalid_utf8_git_wire_name_fails_closed(self):
    with patch("repo_workflow.classification.git_bytes") as run:
      run.return_value.stdout = b"invalid-\xff.txt\0"
      with self.assertRaisesRegex(ClassificationError, "cannot determine changed files"):
        changed_paths(Path("."), "HEAD~1")

  def test_unterminated_git_wire_record_fails_closed(self):
    with patch("repo_workflow.classification.git_bytes") as run:
      run.return_value.stdout = b"docs/test.md"
      with self.assertRaisesRegex(ClassificationError, "unterminated"):
        changed_paths(Path("."), "HEAD~1")

  def test_portable_slash_path_from_git_protocol(self):
    with patch("repo_workflow.classification.git_bytes") as run:
      run.return_value.stdout = b"docs/a.md\0"
      self.assertEqual(changed_paths(Path("."), "HEAD~1"), ["docs/a.md"])


if __name__ == "__main__":
  unittest.main()
