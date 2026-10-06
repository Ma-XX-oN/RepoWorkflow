from pathlib import Path
from unittest import mock
import tempfile
import unittest

from repo_workflow.issue_metadata import (
  IssueMetadataError,
  IssueMetadataStore,
  cache_issue_display_metadata,
  refresh_issue_metadata,
)
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.repo_info_adapter import RepoInfoError
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


def graph():
  return RelationshipGraph(issues={
    "10": IssueRelationships("Ten", ()),
    "20": IssueRelationships("Twenty", ("10",)),
  })


def provider_value(number: int, title: str) -> dict:
  return {
    "schema_version": 1,
    "number": number,
    "title": title,
    "state": "open",
    "link": f"https://example.invalid/issues/{number}",
  }


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

  def test_offline_title_comes_from_canonical_ticket_state(self):
    with mock.patch(
      "repo_workflow.issue_metadata.issue_info",
      side_effect=AssertionError("provider touched during offline read"),
    ):
      self.assertEqual(
        IssueMetadataStore(self.root).issue(20).title,
        "Twenty",
      )
      with self.assertRaisesRegex(
        IssueMetadataError,
        "display metadata is incomplete",
      ):
        IssueMetadataStore(self.root).display_issue(20)

  def test_complete_refresh_updates_server_authoritative_titles_and_display(self):
    values = {
      10: provider_value(10, "Ten renamed"),
      20: provider_value(20, "Twenty"),
    }
    with mock.patch(
      "repo_workflow.issue_metadata.issue_info",
      side_effect=lambda _root, _config, number: values[number],
    ):
      refreshed = refresh_issue_metadata(
        self.root,
        {},
        self.writer,
      )

    self.assertEqual(refreshed.issues[10].title, "Ten renamed")
    self.assertEqual(
      RelationshipStore(self.root).issue(10).title,
      "Ten renamed",
    )
    self.assertEqual(refreshed.issues[20].state, "open")
    self.assertEqual(
      refreshed.issues[20].link,
      "https://example.invalid/issues/20",
    )

  def test_scoped_refresh_reads_only_requested_issue(self):
    calls = []
    with mock.patch(
      "repo_workflow.issue_metadata.issue_info",
      side_effect=lambda _root, _config, number: (
        calls.append(number)
        or provider_value(number, f"Issue {number}")
      ),
    ):
      refresh_issue_metadata(
        self.root,
        {},
        self.writer,
        (10,),
      )
    self.assertEqual(calls, [10])
    self.assertEqual(
      RelationshipStore(self.root).issue(10).title,
      "Issue 10",
    )
    self.assertEqual(
      RelationshipStore(self.root).issue(20).title,
      "Twenty",
    )

  def test_scoped_refresh_rejects_unknown_local_issue_before_provider(self):
    with mock.patch(
      "repo_workflow.issue_metadata.issue_info",
      side_effect=AssertionError("provider must not be called"),
    ):
      with self.assertRaisesRegex(
        IssueMetadataError,
        "outside canonical ticket state",
      ):
        refresh_issue_metadata(
          self.root,
          {},
          self.writer,
          (99,),
        )

  def test_provider_failure_preserves_prior_title_and_display(self):
    with mock.patch(
      "repo_workflow.issue_metadata.issue_info",
      side_effect=lambda _root, _config, number: provider_value(
        number,
        f"Server {number}",
      ),
    ):
      original = refresh_issue_metadata(
        self.root,
        {},
        self.writer,
      )
    original_graph = RelationshipStore(self.root).read()

    with mock.patch(
      "repo_workflow.issue_metadata.issue_info",
      side_effect=RepoInfoError("provider unavailable"),
    ):
      with self.assertRaisesRegex(IssueMetadataError, "provider unavailable"):
        refresh_issue_metadata(
          self.root,
          {},
          self.writer,
          (10,),
        )

    self.assertEqual(RelationshipStore(self.root).read(), original_graph)
    self.assertEqual(IssueMetadataStore(self.root).read(), original)

  def test_invalid_provider_display_value_preserves_state(self):
    before = RelationshipStore(self.root).read()
    with mock.patch(
      "repo_workflow.issue_metadata.issue_info",
      return_value={
        "schema_version": 1,
        "number": 10,
        "title": "Changed",
        "state": "unknown",
        "link": "https://example.invalid/10",
      },
    ):
      with self.assertRaisesRegex(IssueMetadataError, "invalid state"):
        refresh_issue_metadata(
          self.root,
          {},
          self.writer,
          (10,),
        )
    self.assertEqual(RelationshipStore(self.root).read(), before)

  def test_already_fetched_display_metadata_is_cached_without_provider_read(self):
    with mock.patch(
      "repo_workflow.issue_metadata.issue_info",
      side_effect=AssertionError("provider must not be called"),
    ):
      cached = cache_issue_display_metadata(
        self.root,
        {
          10: provider_value(10, "Ten"),
          20: provider_value(20, "Twenty"),
        },
        self.writer,
      )
    self.assertTrue(cached.issues[10].display_complete)
    self.assertTrue(cached.issues[20].display_complete)

  def test_cache_rejects_title_disagreement(self):
    before = RelationshipStore(self.root).read()
    with self.assertRaisesRegex(
      IssueMetadataError,
      "provider title differs",
    ):
      cache_issue_display_metadata(
        self.root,
        {10: provider_value(10, "Wrong")},
        self.writer,
      )
    self.assertEqual(RelationshipStore(self.root).read(), before)

  def test_missing_issue_fails_explicitly_without_provider(self):
    with mock.patch(
      "repo_workflow.issue_metadata.issue_info",
      side_effect=AssertionError("provider touched during offline read"),
    ):
      with self.assertRaisesRegex(IssueMetadataError, "missing for issue 99"):
        IssueMetadataStore(self.root).issue(99)


if __name__ == "__main__":
  unittest.main()
