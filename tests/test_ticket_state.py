from pathlib import Path
import json
import tempfile
import unittest

from repo_workflow.relationship_store import (
  RelationshipStore,
  RelationshipStoreError,
)
from repo_workflow.relationships import (
  IssueRelationships,
  RelationshipGraph,
)
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


class TicketStateTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    RepoFixture(self.root)
    self.writer = WriterIdentity("agent", "session")

  def tearDown(self):
    self.temp.cleanup()

  def graph(self):
    return RelationshipGraph(issues={
      "10": IssueRelationships("Feature: Ten", ()),
      "20": IssueRelationships("Twenty, with comma", ("10",)),
    })

  def test_csv_is_canonical_and_restart_readable(self):
    first = RelationshipStore(self.root).create(self.graph(), self.writer)
    text = (self.root / ".repoworkflow" / "tickets.csv").read_text(
      encoding="utf-8"
    )
    self.assertEqual(
      text,
      (
        "issue,title,dependencies\n"
        '10,Feature: Ten,\n'
        '20,"Twenty, with comma",10\n'
      ),
    )
    restarted = RelationshipStore(self.root).read()
    self.assertEqual(restarted.graph, first.graph)
    self.assertEqual(restarted.revision, first.revision)

  def test_empty_dependency_set_is_known_not_missing(self):
    RelationshipStore(self.root).create(self.graph(), self.writer)
    self.assertEqual(
      RelationshipStore(self.root).direct_dependencies(10),
      (),
    )
    with self.assertRaisesRegex(RelationshipStoreError, "unknown issue"):
      RelationshipStore(self.root).issue(99)

  def test_invalid_cycle_fails_before_write(self):
    graph = RelationshipGraph(issues={
      "10": IssueRelationships("Ten", ("20",)),
      "20": IssueRelationships("Twenty", ("10",)),
    })
    with self.assertRaisesRegex(Exception, "cycle"):
      RelationshipStore(self.root).create(graph, self.writer)
    self.assertFalse(
      (self.root / ".repoworkflow" / "tickets.csv").exists()
    )

  def test_legacy_projection_uses_exact_synchronized_titles(self):
    graph_path = (
      self.root
      / ".repoworkflow"
      / "state"
      / "relationships"
      / "graph.json"
    )
    metadata_path = (
      self.root
      / ".repoworkflow"
      / "state"
      / "issues"
      / "metadata.json"
    )
    graph_path.parent.mkdir(parents=True)
    metadata_path.parent.mkdir(parents=True)
    graph_path.write_text(json.dumps({
      "revision": 7,
      "value": {
        "schema_version": 2,
        "issues": {
          "10": {
            "umbrella": None,
            "shared_umbrellas": [],
            "depends_on": [],
            "umbrella_depends_on": [],
            "parent": "main",
          },
          "20": {
            "umbrella": "1",
            "shared_umbrellas": ["50"],
            "depends_on": ["10"],
            "umbrella_depends_on": ["40"],
            "parent": "issue-10",
          },
        },
      },
    }), encoding="utf-8")
    metadata_path.write_text(json.dumps({
      "value": {
        "schema_version": 2,
        "issues": {
          "10": {
            "number": 10,
            "title": "Ten",
            "state": "open",
            "link": "https://example.invalid/10",
          },
          "20": {
            "number": 20,
            "title": "Twenty",
            "state": "open",
            "link": "https://example.invalid/20",
          },
        },
      },
    }), encoding="utf-8")

    migrated = RelationshipStore(self.root).migrate_legacy(self.writer)

    self.assertEqual(migrated.graph.issue(10).title, "Ten")
    self.assertEqual(migrated.graph.issue(20).depends_on, ("10",))
    self.assertFalse(
      hasattr(migrated.graph.issue(20), "umbrella")
    )
    self.assertFalse(
      hasattr(migrated.graph.issue(20), "parent")
    )
    self.assertTrue(
      (self.root / ".repoworkflow" / "tickets.csv").exists()
    )

  def test_legacy_projection_requires_title_source(self):
    graph_path = (
      self.root
      / ".repoworkflow"
      / "state"
      / "relationships"
      / "graph.json"
    )
    graph_path.parent.mkdir(parents=True)
    graph_path.write_text(json.dumps({
      "revision": 0,
      "value": {
        "schema_version": 2,
        "issues": {
          "10": {
            "umbrella": None,
            "shared_umbrellas": [],
            "depends_on": [],
            "umbrella_depends_on": [],
            "parent": "main",
          },
        },
      },
    }), encoding="utf-8")
    with self.assertRaisesRegex(
      RelationshipStoreError,
      "titles are missing",
    ):
      RelationshipStore(self.root).read()


class RepositoryTicketStateTests(unittest.TestCase):
  def setUp(self):
    self.root = Path(__file__).resolve().parents[1]
    self.store = RelationshipStore(self.root)
    self.audit = json.loads(
      (
        self.root
        / ".repoworkflow"
        / "dependency-audit-v2.json"
      ).read_text(encoding="utf-8")
    )

  def test_committed_ticket_state_matches_reviewed_dependency_audit(self):
    graph = self.store.read().graph
    audited = self.audit["issues"]

    self.assertEqual(set(graph.issues), set(audited))
    for issue, expected in audited.items():
      actual = graph.issue(issue)
      self.assertEqual(actual.title, expected["title"], issue)
      self.assertEqual(
        actual.depends_on,
        tuple(str(x) for x in expected["dependencies"]),
        issue,
      )

  def test_dependency_audit_retains_high_risk_repairs(self):
    expected = {
      5: ("107",),
      16: ("110",),
      27: ("96", "306", "313"),
      51: ("5", "27", "52", "53", "54", "56", "58", "135"),
      205: ("215", "218", "223", "305", "306", "307"),
      303: ("309", "313"),
      305: ("208", "217", "219", "304"),
      313: ("7", "114", "115", "304"),
      320: ("304", "305", "318"),
      342: ("145", "208", "321", "341"),
      403: ("408",),
      409: ("413",),
      415: ("422",),
    }
    for issue, dependencies in expected.items():
      self.assertEqual(
        self.store.direct_dependencies(issue),
        dependencies,
        issue,
      )

  def test_reviewed_graph_has_no_closed_issue_blocked_by_open_issue(self):
    audited = self.audit["issues"]
    for issue, value in audited.items():
      if value["state"] != "closed":
        continue
      for dependency in value["dependencies"]:
        dependency_state = audited[str(dependency)]["state"]
        self.assertNotEqual(
          dependency_state,
          "open",
          f"closed #{issue} is blocked by open #{dependency}",
        )


if __name__ == "__main__":
  unittest.main()
