from pathlib import Path
import tempfile
import unittest

from repo_workflow.actions_policy import ActionsPolicyError, check_actions_policy


class ActionsPolicyTests(unittest.TestCase):
  def setup_paths(self, root: Path):
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    engine = root / "RepoWorkflow"
    (engine / "templates" / "github").mkdir(parents=True)
    return workflows, engine

  def test_exact_canonical_adapter_passes(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      workflows, engine = self.setup_paths(root)
      canonical = "name: CI\n"
      (engine / "templates" / "github" / "ci.yml").write_text(canonical)
      (workflows / "ci.yml").write_text(canonical)
      check_actions_policy(root, engine)

  def test_modified_adapter_is_rejected(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      workflows, engine = self.setup_paths(root)
      (engine / "templates" / "github" / "ci.yml").write_text("name: CI\n")
      (workflows / "ci.yml").write_text("name: changed\n")
      with self.assertRaises(ActionsPolicyError):
        check_actions_policy(root, engine)

  def test_extra_workflow_is_rejected(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      workflows, engine = self.setup_paths(root)
      (engine / "templates" / "github" / "ci.yml").write_text("name: CI\n")
      (workflows / "ci.yml").write_text("name: CI\n")
      (workflows / "extra.yml").write_text("name: extra\n")
      with self.assertRaises(ActionsPolicyError):
        check_actions_policy(root, engine)

  def test_explicit_migration_workflow_can_coexist_with_canonical_adapter(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      workflows, engine = self.setup_paths(root)
      (engine / "templates" / "github" / "ci.yml").write_text("name: CI\n")
      (workflows / "ci.yml").write_text("name: CI\n")
      (workflows / "legacy-artifact.yml").write_text("name: legacy\n")
      check_actions_policy(root, engine, migration_workflows=["legacy-artifact.yml"])

  def test_migration_allow_list_does_not_hide_undeclared_workflows(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      workflows, engine = self.setup_paths(root)
      (engine / "templates" / "github" / "ci.yml").write_text("name: CI\n")
      (workflows / "ci.yml").write_text("name: CI\n")
      (workflows / "legacy-artifact.yml").write_text("name: legacy\n")
      (workflows / "undeclared.yml").write_text("name: undeclared\n")
      with self.assertRaises(ActionsPolicyError):
        check_actions_policy(root, engine, migration_workflows=["legacy-artifact.yml"])


if __name__ == "__main__":
  unittest.main()
