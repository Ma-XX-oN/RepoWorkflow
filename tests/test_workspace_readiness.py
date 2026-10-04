import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from repo_workflow.lifecycle_store import LifecycleStore
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from repo_workflow.workspace_readiness import readiness_json, workspace_readiness
from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]


def graph():
  def issue(depends_on):
    return {
      "umbrella": None,
      "shared_umbrellas": [],
      "depends_on": depends_on,
      "umbrella_depends_on": [],
      "parent": "main",
    }

  return RelationshipGraph.from_json_value({
    "schema_version": 2,
    "issues": {
      "1": issue([]),
      "2": issue(["1"]),
      "3": issue([]),
      "4": issue([]),
      "5": issue([]),
      "6": issue(["1"]),
    },
  })


class WorkspaceReadinessTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.repo = Path(self.temp.name) / "repo"
    self.repo.mkdir()
    self.fx = RepoFixture(self.repo)
    self.writer = WriterIdentity("agent-a", "session-1")
    RelationshipStore(self.repo).create(graph(), self.writer)
    self.lifecycle = LifecycleStore(self.repo)

  def tearDown(self):
    self.temp.cleanup()

  def transition(self, issue, name, revision):
    return self.lifecycle.transition(
      issue,
      name,
      "candidate",
      0,
      self.writer,
      revision,
    )

  def test_projection_distinguishes_dependencies_and_lifecycle_states(self):
    one = self.transition(1, "start", None)
    one = self.transition(1, "accept", one.revision)
    one = self.transition(1, "complete", one.revision)

    three = self.transition(3, "start", None)

    four = self.transition(4, "start", None)
    self.transition(4, "accept", four.revision)

    five = self.transition(5, "start", None)
    self.transition(5, "abort", five.revision)

    results = {result.issue: result for result in workspace_readiness(self.repo)}

    self.assertEqual(results["1"].status, "terminal")
    self.assertEqual(results["2"].status, "ready")
    self.assertEqual(results["3"].status, "active")
    self.assertEqual(results["4"].status, "accepted")
    self.assertEqual(results["5"].status, "ready")
    self.assertEqual(results["6"].status, "ready")

  def test_unresolved_direct_dependency_is_exact_blocker(self):
    results = {result.issue: result for result in workspace_readiness(self.repo)}

    self.assertEqual(results["2"].status, "blocked")
    self.assertEqual(results["2"].blockers, ("1",))
    self.assertEqual(results["6"].blockers, ("1",))

  def test_non_dependency_relationships_do_not_block(self):
    result = {item.issue: item for item in workspace_readiness(self.repo)}["1"]

    self.assertEqual(result.status, "ready")
    self.assertEqual(result.blockers, ())

  def test_json_projection_is_deterministic_and_lists_ready_exactly(self):
    value = readiness_json(self.repo)

    self.assertEqual(value["ready"], [1, 3, 4, 5])
    self.assertEqual(
      [item["issue"] for item in value["issues"]],
      [1, 2, 3, 4, 5, 6],
    )

  def test_workspace_ready_cli_returns_machine_readable_projection(self):
    completed = subprocess.run(
      [
        sys.executable,
        str(ROOT / "repo_workflow.py"),
        "--root",
        str(self.repo),
        "workspace",
        "ready",
      ],
      capture_output=True,
      text=True,
      env=dict(os.environ),
    )

    self.assertEqual(completed.returncode, 0, completed.stderr)
    value = json.loads(completed.stdout)
    self.assertEqual(value["ready"], [1, 3, 4, 5])
    self.assertEqual(value["issues"][1]["status"], "blocked")
    self.assertEqual(value["issues"][1]["blockers"], [1])

  def test_missing_relationship_graph_fails_closed(self):
    other = Path(self.temp.name) / "other"
    other.mkdir()
    subprocess.run(["git", "init"], cwd=other, check=True, capture_output=True)

    with self.assertRaises(Exception):
      workspace_readiness(other)


if __name__ == "__main__":
  unittest.main()
