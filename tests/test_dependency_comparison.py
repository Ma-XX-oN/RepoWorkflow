import unittest

from repo_workflow.dependency_comparison import (
  DependencyComparisonStatus,
  compare_dependencies,
)


class DependencyComparisonTests(unittest.TestCase):
  def test_empty_sets_match(self):
    result = compare_dependencies([], [])
    self.assertEqual(result.status, DependencyComparisonStatus.MATCH)
    self.assertEqual(result.additions, ())
    self.assertEqual(result.removals, ())

  def test_source_only_reports_additions(self):
    result = compare_dependencies([9, 2], [])
    self.assertEqual(result.status, DependencyComparisonStatus.SOURCE_ONLY)
    self.assertEqual(result.source, (2, 9))
    self.assertEqual(result.additions, (2, 9))
    self.assertEqual(result.removals, ())

  def test_destination_only_reports_removals(self):
    result = compare_dependencies([], [9, 2])
    self.assertEqual(result.status, DependencyComparisonStatus.DESTINATION_ONLY)
    self.assertEqual(result.removals, (2, 9))

  def test_reordered_duplicates_are_semantically_identical(self):
    result = compare_dependencies([9, 2, 9], [2, 9])
    self.assertEqual(result.status, DependencyComparisonStatus.MATCH)
    self.assertEqual(result.source, (2, 9))
    self.assertEqual(result.destination, (2, 9))

  def test_overlapping_difference_is_conflict_and_actionable(self):
    result = compare_dependencies([2, 9], [9, 54])
    self.assertEqual(result.status, DependencyComparisonStatus.CONFLICT)
    self.assertEqual(result.additions, (2,))
    self.assertEqual(result.removals, (54,))

  def test_comparison_does_not_mutate_inputs(self):
    source = [9, 2, 9]
    destination = [54, 9]
    compare_dependencies(source, destination)
    self.assertEqual(source, [9, 2, 9])
    self.assertEqual(destination, [54, 9])

  def test_invalid_dependency_ids_fail(self):
    for values in ([0], [-1], [True], ["2"]):
      with self.subTest(values=values):
        with self.assertRaises(ValueError):
          compare_dependencies(values, [])


if __name__ == "__main__":
  unittest.main()
