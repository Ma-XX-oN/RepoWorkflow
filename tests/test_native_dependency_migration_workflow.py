from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (
  ROOT
  / ".github"
  / "workflows"
  / "native-dependency-migration-v1.yml"
)


class NativeDependencyMigrationWorkflowTests(unittest.TestCase):
  def text(self) -> str:
    return WORKFLOW.read_text(encoding="utf-8")

  def test_trigger_is_dedicated_branch_and_one_trigger_file(self):
    text = self.text()
    self.assertIn("migration/native-dependencies-v1", text)
    self.assertIn(
      ".repoworkflow/migrations/run-native-dependencies-v1",
      text,
    )
    self.assertNotIn("workflow_dispatch:", text)
    self.assertNotIn("- main", text)

  def test_permissions_allow_issue_mutation_but_not_content_write(self):
    text = self.text()
    self.assertIn("contents: read", text)
    self.assertIn("issues: write", text)
    self.assertNotIn("contents: write", text)

  def test_dry_run_precedes_apply_and_conflicts_stop_apply(self):
    text = self.text()
    dry = text.index("--report migration-dry-run.json")
    conflict = text.index("conflicting native dependency sets")
    apply = text.index("--apply")
    self.assertLess(dry, conflict)
    self.assertLess(conflict, apply)

  def test_apply_requires_full_matching_readback_and_emits_certification(self):
    text = self.text()
    self.assertIn("--report migration-readback.json", text)
    self.assertIn('"DESTINATION_EMPTY": 0', text)
    self.assertIn('"CONFLICT": 0', text)
    self.assertIn("RWF_PROVIDER_READBACK_SHA256=", text)
    self.assertIn("RWF_CERTIFICATION_JSON=", text)


if __name__ == "__main__":
  unittest.main()
