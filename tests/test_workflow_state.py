import unittest

from repo_workflow.workflow_state import (
  WorkflowFacts,
  derive_plan,
  state_name,
)


class WorkflowStateTests(unittest.TestCase):
  def test_task_before_regression_exposes_only_regression_transition(self):
    facts = WorkflowFacts(regression="missing")
    plan = derive_plan(facts)
    self.assertEqual(plan.transitions, ("test regression",))
    self.assertEqual(state_name(facts), "regression required")
    self.assertIn("missing regression validation", plan.blocks[0])

  def test_regression_fail_retries_regression(self):
    facts = WorkflowFacts(regression="FAIL")
    plan = derive_plan(facts)
    self.assertEqual(plan.transitions, ("test regression",))
    self.assertEqual(state_name(facts), "regression required")
    self.assertTrue(any("failed" in block for block in plan.blocks))

  def test_regression_incomplete_retries_regression(self):
    facts = WorkflowFacts(regression="INCOMPLETE")
    plan = derive_plan(facts)
    self.assertEqual(plan.transitions, ("test regression",))
    self.assertEqual(state_name(facts), "regression required")

  def test_regression_pass_requires_integration_result(self):
    facts = WorkflowFacts(regression="PASS")
    plan = derive_plan(facts)
    self.assertEqual(
      plan.transitions,
      ("test integration",),
    )
    self.assertEqual(state_name(facts), "integration result pending")

  def test_accepted_task_without_authorization_is_blocked(self):
    facts = WorkflowFacts(
      regression="PASS",
      integration_result="succeeded",
      integration_authorized=False,
    )
    plan = derive_plan(facts)
    self.assertNotIn("integrate", plan.transitions)
    self.assertTrue(any("authorization absent" in block for block in plan.blocks))

  def test_stale_prelim_requires_reintegration(self):
    facts = WorkflowFacts(
      regression="PASS",
      integration_result="succeeded",
      prelim_present=True,
      prelim_base_current=False,
    )
    plan = derive_plan(facts)
    self.assertEqual(plan.transitions, ("reintegrate",))
    self.assertEqual(state_name(facts), "preliminary integration stale")

  def test_invalid_branch_and_version_fail_closed(self):
    facts = WorkflowFacts(branch_valid=False, version_valid=False)
    plan = derive_plan(facts)
    self.assertEqual(plan.transitions, ())
    self.assertEqual(state_name(facts), "workflow state invalid")
    self.assertIn("invalid branch state", plan.blocks)
    self.assertIn("invalid version state", plan.blocks)

  def test_integration_failure_returns_to_regression(self):
    facts = WorkflowFacts(regression="PASS", integration_result="failed")
    plan = derive_plan(facts)
    self.assertEqual(plan.transitions, ("test regression",))
    self.assertEqual(state_name(facts), "regression required")


if __name__ == "__main__":
  unittest.main()
