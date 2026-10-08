import unittest

from repo_workflow.lane_projection import ProjectionRule
from repo_workflow.lane_relationship_coverage import (
  RelationshipCoverage,
  rule_is_covered,
)


class LaneRelationshipCoverageTests(unittest.TestCase):
  def coverage(self, *modes: str) -> RelationshipCoverage:
    return RelationshipCoverage(
      partial=True,
      rules=tuple(ProjectionRule("7", mode) for mode in modes),
    )

  def test_both_covers_every_mode_for_same_seed(self):
    coverage = self.coverage("both")
    for mode in ("single", "dependencies", "dependents", "both"):
      with self.subTest(mode=mode):
        self.assertTrue(
          rule_is_covered(coverage, ProjectionRule("7", mode))
        )

  def test_single_does_not_cover_directional_modes(self):
    coverage = self.coverage("single")
    self.assertTrue(
      rule_is_covered(coverage, ProjectionRule("7", "single"))
    )
    for mode in ("dependencies", "dependents", "both"):
      with self.subTest(mode=mode):
        self.assertFalse(
          rule_is_covered(coverage, ProjectionRule("7", mode))
        )

  def test_each_direction_covers_single_but_not_other_direction(self):
    dependencies = self.coverage("dependencies")
    self.assertTrue(
      rule_is_covered(dependencies, ProjectionRule("7", "single"))
    )
    self.assertFalse(
      rule_is_covered(dependencies, ProjectionRule("7", "dependents"))
    )

    dependents = self.coverage("dependents")
    self.assertTrue(
      rule_is_covered(dependents, ProjectionRule("7", "single"))
    )
    self.assertFalse(
      rule_is_covered(dependents, ProjectionRule("7", "dependencies"))
    )

  def test_two_directional_rules_together_cover_both(self):
    coverage = self.coverage("dependencies", "dependents")
    self.assertTrue(
      rule_is_covered(coverage, ProjectionRule("7", "both"))
    )

  def test_coverage_is_seed_specific(self):
    coverage = self.coverage("both")
    self.assertFalse(
      rule_is_covered(coverage, ProjectionRule("8", "single"))
    )

  def test_complete_local_state_covers_every_rule(self):
    coverage = RelationshipCoverage(partial=False, rules=())
    self.assertTrue(
      rule_is_covered(coverage, ProjectionRule("99", "both"))
    )


if __name__ == "__main__":
  unittest.main()
