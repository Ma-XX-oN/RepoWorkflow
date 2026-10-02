import unittest

from repo_workflow.workflow_state import (
  WorkflowFacts,
  completion_candidates,
  derive_plan,
)


class WorkflowStateTests(unittest.TestCase):
  def test_task_before_regression_exposes_only_regression_transition(self):
    plan = derive_plan(WorkflowFacts(regression="missing"))
    self.assertEqual(plan.transitions, ("validate regression",))
    self.assertIn("missing regression validation", plan.blocks[0])

  def test_regression_fail_blocks_integration_and_retries_regression(self):
    plan = derive_plan(WorkflowFacts(regression="FAIL"))
    self.assertEqual(plan.transitions, ("validate regression",))
    self.assertTrue(any("failed" in block for block in plan.blocks))
    self.assertFalse(any("integration succeeded" in item for item in plan.transitions))

  def test_regression_pass_requires_automatic_integration_transition(self):
    plan = derive_plan(WorkflowFacts(regression="PASS"))
    self.assertEqual(plan.transitions, ("validate integration",))

  def test_accepted_task_without_authorization_is_merge_blocked(self):
    plan = derive_plan(WorkflowFacts(
      regression="PASS",
      automatic_integration="PASS",
      integration_authorized=False,
    ))
    self.assertNotIn("integrate", plan.transitions)
    self.assertTrue(any("explicit authorization absent" in block for block in plan.blocks))

  def test_stale_prelim_requires_reintegration_and_blocks_merge(self):
    plan = derive_plan(WorkflowFacts(
      regression="PASS",
      automatic_integration="PASS",
      prelim_present=True,
      prelim_base_current=False,
    ))
    self.assertEqual(plan.transitions, ("reintegrate",))
    self.assertTrue(any("stale integration base" in block for block in plan.blocks))

  def test_regression_incomplete_retries_only_regression(self):
    plan = derive_plan(WorkflowFacts(regression="INCOMPLETE"))
    self.assertEqual(plan.transitions, ("validate regression",))
    self.assertTrue(any("incomplete" in block for block in plan.blocks))

  def test_integration_failure_returns_to_regression(self):
    plan = derive_plan(WorkflowFacts(
      regression="PASS",
      automatic_integration="FAIL",
    ))
    self.assertEqual(plan.transitions, ("validate regression",))
    self.assertTrue(
      any("previous automatic integration failed" in block for block in plan.blocks)
    )

  def test_authorized_accepted_task_exposes_integration_transition(self):
    plan = derive_plan(WorkflowFacts(
      regression="PASS",
      automatic_integration="PASS",
      integration_authorized=True,
    ))
    self.assertEqual(plan.transitions, ("integrate",))
    self.assertEqual(plan.blocks, ())

  def test_invalid_branch_and_version_fail_closed(self):
    plan = derive_plan(WorkflowFacts(branch_valid=False, version_valid=False))
    self.assertEqual(plan.transitions, ())
    self.assertIn("invalid branch state", plan.blocks)
    self.assertIn("invalid version state", plan.blocks)

  def test_completion_exposes_documented_version_surface(self):
    plan = derive_plan(WorkflowFacts(regression="missing"))
    self.assertEqual(
      completion_candidates(plan, ["version", ""]),
      ["--json", "integrate", "release-major", "task"],
    )
    self.assertEqual(
      completion_candidates(plan, ["version", "task", ""]),
      ["issue"],
    )
    self.assertEqual(
      completion_candidates(plan, ["version", "integrate", "increment", ""]),
      ["minor", "patch"],
    )

  def test_completion_is_projection_of_plan(self):
    automatic = derive_plan(WorkflowFacts(regression="PASS"))
    self.assertEqual(
      completion_candidates(automatic, ["validate", "integration", ""]),
      ["--automatic", "--group"],
    )

    manual = derive_plan(WorkflowFacts(
      regression="PASS",
      automatic_integration="PASS",
      manual_integration_required=True,
    ))
    self.assertEqual(
      completion_candidates(manual, ["validate", "integration", ""]),
      ["failed", "succeeded"],
    )
    self.assertEqual(
      completion_candidates(manual, ["validate", "integration", "s"]),
      ["succeeded"],
    )


if __name__ == "__main__":
  unittest.main()
