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
from repo_workflow.state_store import WriterIdentity, durable_store
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
    durable_store(self.root).create(
      "issues/metadata",
      {
        "schema_version": 1,
        "issues": {
          "10": {"number": 10, "title": "Ten"},
        },
      },
      WriterIdentity("legacy", "legacy"),
    )

    store = IssueMetadataStore(self.root)
    self.assertEqual(store.issue(10).title, "Ten")
    with self.assertRaisesRegex(
      IssueMetadataError,
      "display metadata is incomplete",
    ):
      store.display_issue(10)

  def test_scoped_refresh_migrates_one_legacy_entry_without_rereading_others(self):
    durable_store(self.root).create(
      "issues/metadata",
      {
        "schema_version": 1,
        "issues": {
          "10": {"number": 10, "title": "Ten"},
          "20": {"number": 20, "title": "Twenty"},
        },
      },
      WriterIdentity("legacy", "legacy"),
    )
    calls: list[int] = []

    def provider(_root, _config, number):
      calls.append(number)
      return {
        "schema_version": 1,
        "number": number,
        "title": "Ten refreshed" if number == 10 else "Twenty refreshed",
        "state": "open",
        "link": f"https://example.invalid/issues/{number}",
      }

    with mock.patch(
      "repo_workflow.issue_metadata.issue_info",
      side_effect=provider,
    ):
      first = refresh_issue_metadata(
        self.root,
        {},
        self.writer,
        (10,),
      )

    self.assertEqual(calls, [10])
    self.assertTrue(first.issues[10].display_complete)
    self.assertFalse(first.issues[20].display_complete)
    self.assertEqual(first.issues[20].title, "Twenty")

    restarted = IssueMetadataStore(self.root)
    self.assertEqual(restarted.issue(20).title, "Twenty")
    with self.assertRaisesRegex(
      IssueMetadataError,
      "display metadata is incomplete",
    ):
      restarted.display_issue(20)

    calls.clear()
    with mock.patch(
      "repo_workflow.issue_metadata.issue_info",
      side_effect=provider,
    ):
      second = refresh_issue_metadata(
        self.root,
        {},
        self.writer,
        (20,),
      )

    self.assertEqual(calls, [20])
    self.assertEqual(second.issues[10], first.issues[10])
    self.assertTrue(second.issues[20].display_complete)

  def test_schema_v2_rejects_mixed_incomplete_state_link_shapes(self):
    store = durable_store(self.root)
    invalid = (
      {"state": None, "link": "https://example.invalid/issues/10"},
      {"state": "open", "link": None},
      {"state": "unknown", "link": None},
    )
    for index, partial in enumerate(invalid):
      with self.subTest(partial=partial):
        key = f"issues/metadata-{index}"
        store.create(
          key,
          {
            "schema_version": 2,
            "issues": {
              "10": {
                "number": 10,
                "title": "Ten",
                **partial,
              },
            },
          },
          self.writer,
        )
        record = store.read(key)
        with self.assertRaises(ValueError):
          from repo_workflow.issue_metadata import _parse_snapshot
          _parse_snapshot(record["value"])

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
    self.assertEqual(
      second.issues[10].title,
      "Changed Ten",
    )
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

  def test_provider_invalid_state_or_link_fails_without_mutation(self):
    original = refresh_issue_metadata(
      self.root,
      self.provider({10: "Ten", 20: "Twenty"}),
      self.writer,
    )

    with mock.patch(
      "repo_workflow.issue_metadata.issue_info",
      return_value={
        "schema_version": 1,
        "number": 10,
        "title": "Ten",
        "state": "unknown",
        "link": "https://example.invalid/issues/10",
      },
    ):
      with self.assertRaisesRegex(IssueMetadataError, "invalid state"):
        refresh_issue_metadata(
          self.root,
          {},
          self.writer,
          (10,),
        )

    self.assertEqual(IssueMetadataStore(self.root).read(), original)

    with mock.patch(
      "repo_workflow.issue_metadata.issue_info",
      return_value={
        "schema_version": 1,
        "number": 10,
        "title": "Ten",
        "state": "open",
        "link": "",
      },
    ):
      with self.assertRaisesRegex(IssueMetadataError, "empty link"):
        refresh_issue_metadata(
          self.root,
          {},
          self.writer,
          (10,),
        )

    self.assertEqual(IssueMetadataStore(self.root).read(), original)

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
