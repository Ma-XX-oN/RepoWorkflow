"""Freeze the corrected October 17 functional completion DAG (#677)."""
import csv
from pathlib import Path
import unittest


_CSV = Path(__file__).resolve().parents[1] / ".repoworkflow/tickets.csv"
_EDGES = {
  103: {84, 681},
  109: {83, 103, 108, 118, 681, 683},
  583: {109, 582},
  677: {83, 84, 102, 108, 109, 583},
  681: {81, 97, 119},
  683: {82, 83, 84, 102},
}


def dependencies():
  with _CSV.open(encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream))
  values = {}
  for row in rows:
    issue = int(row["issue"])
    if issue in values:
      raise ValueError("duplicate ticket ID")
    values[issue] = {
      int(item) for item in row["dependencies"].split(";") if item
    }
  return values


class October17DependencyClosureTests(unittest.TestCase):
  def test_all_corrected_direct_edges_and_no_deferred_security(self):
    actual = dependencies()
    for issue, expected in _EDGES.items():
      with self.subTest(issue=issue):
        self.assertEqual(actual[issue], expected)
    self.assertNotIn(85, actual[103])
    self.assertNotIn(86, actual[109])
    self.assertNotIn(683, actual[103])
    self.assertNotIn(677, actual[109])

  def test_all_dependencies_exist_and_graph_acyclic(self):
    graph = dependencies()
    completed = set()
    visiting = set()

    def check(issue):
      if issue in visiting:
        raise AssertionError("dependency cycle at #" + str(issue))
      if issue in completed:
        return
      visiting.add(issue)
      for predecessor in graph[issue]:
        self.assertIn(predecessor, graph)
        check(predecessor)
      visiting.remove(issue)
      completed.add(issue)

    for issue in graph:
      check(issue)


if __name__ == "__main__":
  unittest.main()
