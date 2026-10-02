import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from repo_workflow.config import ConfigError, load_config
from repo_workflow.workflow_state import (
  WorkflowFacts,
  derive_plan,
  discover_facts,
  save_local_state,
)
from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "repo_workflow.py"


def _configure_validation_classes(
  root: Path,
  *,
  manual_required: bool = False,
  art_fast: bool = True,
  integration_body: str = "raise SystemExit(0)\n",
) -> None:
  config_path = root / ".ci" / "repoworkflow.json"
  config = json.loads(config_path.read_text(encoding="utf-8"))
  config["environments"][0]["fast"] = art_fast
  config["environments"][0]["groups"] = ["smoke"]
  config["integrationEnvironments"] = [{
    "id": "integration-local",
    "required": True,
    "platform": "any",
    "capabilities": [],
    "groups": ["core"],
    "validationCommand": [sys.executable, "scripts/integration-validate.py"],
  }]
  config["manualIntegrationRequired"] = manual_required
  config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
  (root / "scripts" / "integration-validate.py").write_text(
    integration_body,
    encoding="utf-8",
  )


class ValidationClassStateTests(unittest.TestCase):
  def test_art_pass_requires_automatic_integration(self):
    plan = derive_plan(WorkflowFacts(
      regression="PASS",
      automatic_integration="missing",
    ))
    self.assertEqual(plan.transitions, ("validate integration",))
    self.assertTrue(any("automatic integration" in item for item in plan.blocks))

  def test_ait_pass_without_mit_does_not_invent_manual_gate(self):
    plan = derive_plan(WorkflowFacts(
      regression="PASS",
      automatic_integration="PASS",
      manual_integration_required=False,
      integration_authorized=True,
    ))
    self.assertEqual(plan.transitions, ("integrate",))
    self.assertEqual(plan.blocks, ())

  def test_ait_pass_with_mit_exposes_human_result_only(self):
    plan = derive_plan(WorkflowFacts(
      regression="PASS",
      automatic_integration="PASS",
      manual_integration_required=True,
      manual_integration_result=None,
    ))
    self.assertEqual(
      plan.transitions,
      ("validate integration succeeded", "validate integration failed"),
    )


class ValidationClassCliTests(unittest.TestCase):
  def run_cli(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
      [sys.executable, str(CLI), "--root", str(root), *args],
      text=True,
      capture_output=True,
      check=False,
    )

  def test_fast_art_is_diagnostic_and_does_not_advance_complete_gate(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      _configure_validation_classes(root)
      fx.commit("declare validation classes")
      candidate = fx.head()

      completed = self.run_cli(root, "validate", "regression", "--fast")

      self.assertEqual(completed.returncode, 0, completed.stderr)
      facts = discover_facts(root)
      self.assertEqual(facts.regression, "missing")
      self.assertEqual(fx.head(), candidate)

  def test_group_art_is_diagnostic_and_does_not_advance_complete_gate(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      _configure_validation_classes(root)
      fx.commit("declare validation classes")

      completed = self.run_cli(
        root,
        "validate",
        "regression",
        "--group",
        "smoke",
      )

      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertEqual(discover_facts(root).regression, "missing")

  def test_bare_integration_runs_ait_and_waits_for_required_mit(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      _configure_validation_classes(root, manual_required=True)
      fx.commit("declare validation classes")
      save_local_state(root, fx.head(), regression="PASS")

      completed = self.run_cli(root, "validate", "integration")

      self.assertEqual(completed.returncode, 0, completed.stderr)
      facts = discover_facts(root)
      self.assertEqual(facts.automatic_integration, "PASS")
      self.assertIsNone(facts.manual_integration_result)
      plan = derive_plan(facts)
      self.assertEqual(
        plan.transitions,
        ("validate integration succeeded", "validate integration failed"),
      )

  def test_ait_failure_advances_q_and_resets_r_without_human_result(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root, version="1.0.0-issue.1.3.7")
      _configure_validation_classes(
        root,
        integration_body="raise SystemExit(1)\n",
      )
      fx.commit("declare failing automatic integration")
      save_local_state(root, fx.head(), regression="PASS")

      completed = self.run_cli(root, "validate", "integration")

      self.assertEqual(completed.returncode, 1)
      self.assertEqual(
        (root / "VERSION").read_text(encoding="utf-8").strip(),
        "1.0.0-issue.1.4.1",
      )
      facts = discover_facts(root)
      self.assertEqual(facts.regression, "missing")

  def test_no_mit_requirement_does_not_expose_human_result(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      _configure_validation_classes(root, manual_required=False)
      fx.commit("declare validation classes")
      save_local_state(root, fx.head(), regression="PASS")

      completed = self.run_cli(root, "validate", "integration")

      self.assertEqual(completed.returncode, 0, completed.stderr)
      facts = discover_facts(root)
      self.assertEqual(facts.automatic_integration, "PASS")
      plan = derive_plan(facts)
      self.assertNotIn("validate integration succeeded", plan.transitions)
      self.assertNotIn("validate integration failed", plan.transitions)

  def test_manual_selector_is_rejected_when_mit_is_not_required(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      _configure_validation_classes(root, manual_required=False)
      fx.commit("declare validation classes")
      save_local_state(
        root,
        fx.head(),
        regression="PASS",
        automaticIntegration="PASS",
      )

      completed = self.run_cli(root, "validate", "integration", "--manual")

      self.assertEqual(completed.returncode, 2)
      self.assertIn("manual integration is blocked", completed.stderr)

  def test_explicit_automatic_selector_runs_complete_ait(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      _configure_validation_classes(root)
      fx.commit("declare validation classes")
      save_local_state(root, fx.head(), regression="PASS")

      completed = self.run_cli(
        root,
        "validate",
        "integration",
        "--automatic",
      )

      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertEqual(discover_facts(root).automatic_integration, "PASS")

  def test_integration_group_cannot_satisfy_complete_ait_gate(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      _configure_validation_classes(root)
      fx.commit("declare validation classes")
      save_local_state(root, fx.head(), regression="PASS")

      completed = self.run_cli(
        root,
        "validate",
        "integration",
        "--group",
        "core",
      )

      self.assertEqual(completed.returncode, 0, completed.stderr)
      facts = discover_facts(root)
      self.assertEqual(facts.automatic_integration, "missing")

  def test_automatic_selector_runs_complete_ait(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      _configure_validation_classes(root)
      fx.commit("declare validation classes")
      save_local_state(root, fx.head(), regression="PASS")

      completed = self.run_cli(
        root,
        "validate",
        "integration",
        "--automatic",
      )

      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertEqual(discover_facts(root).automatic_integration, "PASS")

  def test_manual_selector_is_blocked_until_ait_passes(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      _configure_validation_classes(root, manual_required=True)
      fx.commit("declare validation classes")
      save_local_state(root, fx.head(), regression="PASS")

      blocked = self.run_cli(
        root,
        "validate",
        "integration",
        "--manual",
      )
      self.assertEqual(blocked.returncode, 2)

      automatic = self.run_cli(
        root,
        "validate",
        "integration",
        "--automatic",
      )
      self.assertEqual(automatic.returncode, 0, automatic.stderr)
      before = fx.head()
      selected = self.run_cli(
        root,
        "validate",
        "integration",
        "--manual",
      )
      self.assertEqual(selected.returncode, 0, selected.stderr)
      self.assertEqual(fx.head(), before)
      self.assertIn("succeeded or failed", selected.stdout)

  def test_ait_incomplete_retries_same_candidate_without_q_increment(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root, version="1.0.0-issue.1.2.4")
      _configure_validation_classes(
        root,
        integration_body="raise SystemExit(2)\n",
      )
      fx.commit("declare incomplete automatic integration")
      candidate = fx.head()
      save_local_state(root, candidate, regression="PASS")

      completed = self.run_cli(root, "validate", "integration")

      self.assertEqual(completed.returncode, 2)
      self.assertEqual(fx.head(), candidate)
      self.assertEqual(
        (root / "VERSION").read_text(encoding="utf-8").strip(),
        "1.0.0-issue.1.2.4",
      )
      facts = discover_facts(root)
      self.assertEqual(facts.automatic_integration, "INCOMPLETE")
      self.assertEqual(derive_plan(facts).transitions, ("validate integration",))

  def test_no_declared_ait_or_mit_does_not_create_manual_gate(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      save_local_state(root, fx.head(), regression="PASS")

      facts = discover_facts(root)
      self.assertFalse(facts.automatic_integration_required)
      self.assertFalse(facts.manual_integration_required)
      plan = derive_plan(facts)
      self.assertNotIn("validate integration succeeded", plan.transitions)
      self.assertNotIn("validate integration failed", plan.transitions)
      self.assertTrue(any("authorization absent" in block for block in plan.blocks))

  def test_unknown_group_is_actionable_and_nonmutating(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      _configure_validation_classes(root)
      fx.commit("declare validation classes")
      candidate = fx.head()
      save_local_state(root, candidate, regression="PASS")

      completed = self.run_cli(
        root,
        "validate",
        "integration",
        "--group",
        "missing",
      )

      self.assertEqual(completed.returncode, 2)
      self.assertIn("not declared", completed.stderr)
      self.assertEqual(fx.head(), candidate)


class ValidationClassConfigTests(unittest.TestCase):
  def test_duplicate_art_and_ait_environment_ids_are_rejected(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      path = root / ".ci" / "repoworkflow.json"
      config = json.loads(path.read_text(encoding="utf-8"))
      config["integrationEnvironments"] = [{
        **config["environments"][0],
      }]
      path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

      with self.assertRaisesRegex(ConfigError, "duplicate environment id"):
        load_config(root)

  def test_fast_flag_is_rejected_for_ait_environment(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)
      path = root / ".ci" / "repoworkflow.json"
      config = json.loads(path.read_text(encoding="utf-8"))
      config["integrationEnvironments"] = [{
        "id": "integration",
        "required": True,
        "platform": "any",
        "capabilities": [],
        "fast": True,
        "validationCommand": [sys.executable, "scripts/validate.py"],
      }]
      path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

      with self.assertRaisesRegex(ConfigError, "valid only for regression"):
        load_config(root)


if __name__ == "__main__":
  unittest.main()
