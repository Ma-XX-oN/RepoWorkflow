from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SelfCiTests(unittest.TestCase):
  def test_main_green_bootstrap_publishes_exact_stable_tag(self):
    text = (ROOT / ".github" / "workflows" / "self-ci.yml").read_text(
      encoding="utf-8"
    )
    self.assertIn("needs: [classify, validate]", text)
    self.assertIn("github.ref == 'refs/heads/main'", text)
    self.assertEqual(text.count("contents: write"), 1)
    self.assertIn("version=\"$(tr -d '\\r\\n' < VERSION)\"", text)
    self.assertIn("refs/heads/main", text)
    self.assertIn("git ls-remote --heads origin", text)
    self.assertIn("git ls-remote --tags origin", text)
    self.assertIn("github-actions[bot]", text)
    self.assertIn("git tag -a", text)
    self.assertIn("git push origin", text)

  def test_bootstrap_release_requires_plain_semver(self):
    text = (ROOT / ".github" / "workflows" / "self-ci.yml").read_text(
      encoding="utf-8"
    )
    self.assertIn("^[0-9]+\\.[0-9]+\\.[0-9]+$", text)

  def test_docs_only_changes_skip_all_code_testing_jobs(self):
    text = (ROOT / ".github" / "workflows" / "self-ci.yml").read_text(
      encoding="utf-8"
    )
    self.assertIn("python repo_workflow.py classify --base", text)

    for job in (
      "validate",
      "argv-limits",
      "graph-renderer-platform",
      "ticket-merge-platform",
    ):
      self.assertIn(
        (
          f"  {job}:\n"
          "    needs: classify\n"
          "    if: needs.classify.outputs.validation != 'fast'\n"
        ),
        text,
      )

  def test_docs_only_main_push_can_release_without_code_validation(self):
    text = (ROOT / ".github" / "workflows" / "self-ci.yml").read_text(
      encoding="utf-8"
    )
    start = text.index("  release:")
    block = text[start:]
    self.assertIn("needs: [classify, validate]", block)
    self.assertIn("always()", block)
    self.assertIn("needs.classify.outputs.validation == 'fast'", block)
    self.assertIn("needs.validate.result == 'success'", block)


if __name__ == "__main__":
  unittest.main()
