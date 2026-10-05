from pathlib import Path
from unittest import mock
import json
import sys
import tempfile
import unittest

from repo_workflow.issue_metadata import (
  IssueMetadataError,
  IssueMetadataStore,
  refresh_issue_metadata,
)
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


def graph():
  return RelationshipGraph.from_json_value({
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
        "umbrella": None,
        "shared_umbrellas": [],
        "depends_on": ["10"],
        "umbrella_depends_on": [],
        "parent": "issue-10",
      },
    },
  })


class IssueMetadataTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    RepoFixture(self.root)
    self.writer = WriterIdentity("agent-a", "session-1")
    RelationshipStore(self.root).create(graph(), self.writer)

  def tearDown(self):
    self.temp.cleanup()

  def provider(self, titles: dict[int, str], fail: int | None = None) -> dict:
    script = self.root / "scripts" / "metadata-provider.py"
    script.parent.mkdir(exist_ok=True)
    script.write_text(
      "import json, sys\n"
      f"titles = {titles!r}\n"
      f"fail = {fail!r}\n"
      "number = int(sys.argv[-1])\n"
      "if number == fail:\n"
      "  print('provider unavailable', file=sys.stderr)\n"
      "  raise SystemExit(7)\n"
      "print(json.dumps({\n"
      "  'schema_version': 1,\n"
      "  'number': number,\n"
      "  'title': titles[number],\n"
      "  'state': 'open',\n"
      "  'link': f'https://example.invalid/issues/{number}',\n"
      "}))\n",
      encoding="utf-8",
    )
    return {"infoCommand": [sys.executable, str(script)]}

  def test_complete_refresh_persists_all_graph_issues_and_restarts(self):
    refresh_issue_metadata(
      self.root,
      self.provider({10: "Ten", 20: "Twenty"}),
      self.writer,
    )

    restarted = IssueMetadataStore(self.root)
    self.assertEqual(restarted.display_issue(10).title, "Ten")
    self.assertEqual(restarted.display_issue(10).state, "open")
    self.assertEqual(
      restarted.display_issue(20).link,
      "https://example.invalid/issues/20",
    )
    value = restarted.read()
    self.assertEqual(set(value.issues), {10, 20})

  def test_schema_v1_remains_title_readable_but_not_display_complete(self):
    path = self.root / ".repoworkflow/state/issues/metadata.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
      json.dumps({
        "schema_version": 1,
        "revision": 0,
        "writer_id": "legacy",
        "session_id": "legacy",
        "value": {
          "schema_version": 1,
          "issues": {
            "10": {"number": 10, "title": "Ten"},
          },
        },
      }),
      encoding="utf-8",
    )

    store = IssueMetadataStore(self.root)
    self.assertEqual(store.issue(10).title, "Ten")
    with self.assertRaisesRegex(
      IssueMetadataError,
      "display metadata is incomplete",
    ):
      store.display_issue(10)

  def test_scoped_refresh_preserves_other_complete_records(self):
    first = refresh_issue_metadata(
      self.root,
      self.provider({10: "Ten", 20: "Twenty"}),
      self.writer,
    )
    second = refresh_issue_metadata(
      self.root,
      self.provider({10: "Changed Ten", 20: "Ignored"}),
      self.writer,
      (10,),
    )

    self.assertEqual(second.revision, first.revision + 1)
    self.assertEqual(second.display_issue(10).title if hasattr(second, "display_issue") else second.issues[10].title, "Changed Ten")
    self.assertEqual(second.issues[20], first.issues[20])

  def test_scoped_refresh_rejects_issue_outside_canonical_graph(self):
    with self.assertRaisesRegex(
      IssueMetadataError,
      "outside canonical relationship graph",
    ):
      refresh_issue_metadata(
        self.root,
        self.provider({10: "Ten", 20: "Twenty", 99: "Ninety Nine"}),
        self.writer,
        (99,),
      )

  def test_title_change_replaces_complete_snapshot(self):
    first = refresh_issue_metadata(
      self.root,
      self.provider({10: "Old Ten", 20: "Twenty"}),
      self.writer,
    )
    second = refresh_issue_metadata(
      self.root,
      self.provider({10: "New Ten", 20: "Twenty"}),
      self.writer,
    )

    self.assertEqual(second.revision, first.revision + 1)
    self.assertEqual(second.issues[10].title, "New Ten")

  def test_provider_failure_preserves_prior_complete_snapshot(self):
    original = refresh_issue_metadata(
      self.root,
      self.provider({10: "Ten", 20: "Twenty"}),
      self.writer,
    )

    with self.assertRaisesRegex(IssueMetadataError, "provider unavailable"):
      refresh_issue_metadata(
        self.root,
        self.provider({10: "Changed", 20: "Ignored"}, fail=20),
        self.writer,
      )

    self.assertEqual(IssueMetadataStore(self.root).read(), original)

  def test_offline_read_never_touches_provider_adapter(self):
    refresh_issue_metadata(
      self.root,
      self.provider({10: "Ten", 20: "Twenty"}),
      self.writer,
    )

    with mock.patch(
      "repo_workflow.issue_metadata.issue_info",
      side_effect=AssertionError("provider touched during offline read"),
    ):
      self.assertEqual(
        IssueMetadataStore(self.root).display_issue(20).title,
        "Twenty",
      )

  def test_missing_local_metadata_fails_explicitly_without_provider(self):
    with mock.patch(
      "repo_workflow.issue_metadata.issue_info",
      side_effect=AssertionError("provider touched during offline read"),
    ):
      with self.assertRaisesRegex(IssueMetadataError, "record is missing"):
        IssueMetadataStore(self.root).issue(10)

  def test_missing_issue_in_snapshot_fails_explicitly_without_provider(self):
    refresh_issue_metadata(
      self.root,
      self.provider({10: "Ten", 20: "Twenty"}),
      self.writer,
    )

    with mock.patch(
      "repo_workflow.issue_metadata.issue_info",
      side_effect=AssertionError("provider touched during offline read"),
    ):
      with self.assertRaisesRegex(IssueMetadataError, "missing for issue 99"):
        IssueMetadataStore(self.root).issue(99)

  def test_malformed_or_empty_title_snapshot_fails_closed(self):
    path = self.root / ".repoworkflow/state/issues/metadata.json"
    value = json.loads(path.read_text()) if path.exists() else None
    self.assertIsNone(value)

    refresh_issue_metadata(
      self.root,
      self.provider({10: "Ten", 20: "Twenty"}),
      self.writer,
    )
    record = json.loads(path.read_text())
    record["value"]["issues"]["10"]["title"] = ""
    path.write_text(json.dumps(record), encoding="utf-8")

    with self.assertRaisesRegex(IssueMetadataError, "empty title"):
      IssueMetadataStore(self.root).read()


if __name__ == "__main__":
  unittest.main()
