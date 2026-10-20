"""Default READY producer never silently falls back to legacy prelim-main."""
from unittest.mock import patch
import unittest

from repo_workflow.prelim_integration import (
  prepare_ready_prelim, submit_legacy_recorded_ready,
  submit_ready_prelim, validate_ready_prelim,
)
from repo_workflow.prelim_ready import PublishedReady, ReadyPublicationError


G = "11111111-1111-4111-8111-111111111111"
C = "c" * 40
CONFIG = {"repository": {"authoritativeRemote": "origin"}}


class ReadyIntegrationTests(unittest.TestCase):
  def test_first_use_prepares_destination_qualified_local_candidate(self):
    with patch("repo_workflow.prelim_ready_v2_prepare.prepare_destination_prelim",
               return_value=object()) as prepare:
      result = prepare_ready_prelim(
        ".", 123, "refs/heads/issue-123", "issue-100", CONFIG,
        resolve_parent=lambda _: "issue-100", guid=G,
      )
    self.assertIsNotNone(result)
    self.assertEqual(prepare.call_args.args[1:4],
                     ("123", "refs/heads/issue-123", "issue-100"))
    self.assertEqual(prepare.call_args.kwargs["guid"], G)

  def test_first_use_rejects_malformed_issue_without_preparation(self):
    with patch("repo_workflow.prelim_ready_v2_prepare.prepare_destination_prelim"
               ) as prepare:
      with self.assertRaisesRegex(Exception, "invalid READY ticket"):
        prepare_ready_prelim(
          ".", True, "refs/heads/issue-1", "main", CONFIG,
          resolve_parent=lambda _: "main")
    prepare.assert_not_called()

  def test_validation_uses_authenticated_candidate_boundary(self):
    with patch("repo_workflow.prelim_ready_v2_validation.validate_destination_prelim",
               return_value={"value": {"outcome": "PASS"}}) as validate:
      result = validate_ready_prelim(
        ".", G, CONFIG, regression="hosted-regression",
        integration="hosted-integration")
    self.assertEqual(result["value"]["outcome"], "PASS")
    self.assertEqual(validate.call_args.args[1], G)

  def test_default_ready_event_routes_only_to_qualified_publisher(self):
    expected = PublishedReady(
      "refs/heads/PRELIM-issue-123/issue-100-" + G, C, "ready-" + G)
    with (
      patch("repo_workflow.prelim_ready_v2_publish.publish_destination_prelim",
            return_value=expected) as publish,
      patch("repo_workflow.prelim_ready_recorded.publish_recorded_ready_certified"
            ) as legacy,
      patch("repo_workflow.prelim_integration.dispatch_configured") as pr,
    ):
      result = submit_ready_prelim(
        ".", G, CONFIG, ticket=123, destination="issue-100",
        request_id="ready-" + G, backend=object(),
        resolve_parent=lambda _: "issue-100")
    self.assertEqual(result, expected)
    self.assertEqual(publish.call_args.kwargs["destination"], "issue-100")
    legacy.assert_not_called()
    pr.assert_not_called()

  def test_missing_v2_identity_cannot_invoke_legacy_fallback(self):
    with (
      patch("repo_workflow.prelim_ready_v2_publish.publish_destination_prelim",
            side_effect=ReadyPublicationError(
              "independent v2 PASS identity absent")) as qualified,
      patch("repo_workflow.prelim_ready_recorded.publish_recorded_ready_certified"
            ) as legacy,
    ):
      with self.assertRaisesRegex(ReadyPublicationError, "PASS identity absent"):
        submit_ready_prelim(
          ".", G, CONFIG, ticket=123, destination="main",
          request_id="ready-" + G, backend=object(),
          resolve_parent=lambda _: "main")
    qualified.assert_called_once()
    legacy.assert_not_called()

  def test_historical_producer_only_via_explicit_bridge(self):
    expected = PublishedReady(
      "refs/heads/PRELIM-issue-123/main-" + G, C, "ready-" + G)
    with patch(
      "repo_workflow.prelim_ready_recorded.publish_recorded_ready_certified",
      return_value=expected,
    ) as legacy:
      result = submit_legacy_recorded_ready(
        ".", G, CONFIG, ticket=123, destination="main",
        request_id="ready-" + G, backend=object(),
        resolve_parent=lambda _: "main")
    self.assertEqual(result, expected)
    self.assertEqual(legacy.call_args.kwargs["guid"], G)


if __name__ == "__main__":
  unittest.main()
