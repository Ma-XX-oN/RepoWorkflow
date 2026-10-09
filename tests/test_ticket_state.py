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
from repo_workflow.lifecycle_store import LifecycleStore
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


  def test_explicit_state_refresh_upgrades_csv_and_preserves_snapshot(self):
    store = RelationshipStore(self.root)
    store.create(self.graph(), self.writer)
    initial = store.read()
    self.assertIsNone(initial.states)
    refreshed = store.refresh_states(self.writer)
    self.assertEqual(
      {issue: value.state for issue, value in refreshed.states.items()},
      {"10": "not_started", "20": "not_started"},
    )
    self.assertIsNone(refreshed.states["10"].lifecycle_revision)
    text = store.path.read_text(encoding="utf-8")
    self.assertTrue(text.startswith(
      "issue,title,dependencies,state,state_revision\\n"
    ))
    self.assertEqual(store.read().states, refreshed.states)

    started = LifecycleStore(self.root).transition(
      10, "start", "candidate", 0, self.writer, None,
    )
    self.assertEqual(started.lifecycle.state, "active")
    self.assertEqual(store.read().states["10"].state, "not_started")
    changed = store.refresh_states(self.writer)
    self.assertEqual(changed.states["10"].state, "active")
    self.assertEqual(changed.states["10"].lifecycle_revision, 0)
    self.assertEqual(changed.states["20"].state, "not_started")

  def test_graph_replacement_preserves_cached_status(self):
    store = RelationshipStore(self.root)
    store.create(self.graph(), self.writer)
    refreshed = store.refresh_states(self.writer)
    modified = RelationshipGraph(issues={
      "10": IssueRelationships("Feature: Ten", ()),
      "20": IssueRelationships("Revised", ("10",)),
    })
    updated = store.replace(refreshed.revision, modified, self.writer)
    self.assertEqual(updated.states, refreshed.states)
    self.assertEqual(updated.graph.issue(20).title, "Revised")

  def test_malformed_cached_state_is_rejected(self):
    store = RelationshipStore(self.root)
    store.create(self.graph(), self.writer)
    store.refresh_states(self.writer)
    old = store.path.read_text(encoding="utf-8")
    for replacement in ("completed,", "active,", "unknown,"):
      with self.subTest(state=replacement):
        store.path.write_text(
          old.replace("not_started,", replacement, 1),
          encoding="utf-8",
        )
        with self.assertRaises(RelationshipStoreError):
          store.read()
    store.path.write_text(old, encoding="utf-8")

  def test_stale_refresh_revision_preserves_prior_csv(self):
    store = RelationshipStore(self.root)
    store.create(self.graph(), self.writer)
    first = store.refresh_states(self.writer)
    with self.assertRaisesRegex(RelationshipStoreError, "stale ticket-state"):
      store._write(first.graph, first.revision - 1, first.states)
    self.assertEqual(store.read(), first)

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

  def test_reviewed_dependency_manifest_population_is_preserved(self):
    manifest_path = (
      self.root
      / ".repoworkflow"
      / "migrations"
      / "native-dependencies-v1.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    reviewed = set(manifest["issues"])
    current = set(self.store.read().graph.issues)
    self.assertTrue(reviewed <= current)
    self.assertGreaterEqual(len(current), 233)

  def test_dependency_audit_corrections_are_retained(self):
    expected = {
      5: (107,),
      16: (110,),
      17: (83, 103),
      27: (74, 96),
      51: (
        5, 16, 17, 18, 19, 27, 52, 53, 54, 55, 56, 57, 58,
        122, 123, 135,
      ),
      96: (306, 313, 350),
      205: (208, 215, 218, 223, 305, 306, 307),
      208: (214,),
      230: (64, 227, 229, 240),
      233: (227, 230, 240),
      298: (90, 297, 300),
      303: (307, 309, 312, 313, 320),
      305: (208, 217, 219, 304),
      313: (7, 73, 114, 115, 304),
      320: (304, 305, 318),
      321: (208, 305, 320, 327),
      340: (145, 208, 217, 219, 229, 346),
      342: (145, 208, 321, 341),
      343: (217, 219, 341, 342, 349, 359),
      382: (388,),
      390: (396,),
      398: (400, 401),
      403: (408,),
      406: (404, 405),
      408: (404, 405, 406, 407),
      409: (413,),
      413: (410, 411, 412),
      415: (422,),
    }
    for issue, dependencies in expected.items():
      with self.subTest(issue=issue):
        self.assertEqual(
          self.store.direct_dependencies(issue),
          tuple(str(value) for value in dependencies),
        )

  def test_stale_parent_blockers_are_absent(self):
    self.assertNotIn("205", self.store.direct_dependencies(305))
    self.assertNotIn("27", self.store.direct_dependencies(313))
    self.assertNotIn("303", self.store.direct_dependencies(320))
    self.assertNotIn("228", self.store.direct_dependencies(230))
    self.assertNotIn("228", self.store.direct_dependencies(233))


if __name__ == "__main__":
  unittest.main()
