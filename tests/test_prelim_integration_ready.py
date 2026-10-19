"""Branch-as-READY submission bypasses old PR/queue request."""
from unittest.mock import patch
import unittest

from repo_workflow.prelim_integration import submit_ready_prelim
from repo_workflow.prelim_ready import PublishedReady

G = "11111111-1111-4111-8111-111111111111"
C = "c"*40


class ReadyIntegrationTests(unittest.TestCase):
  def test_calls_exact_certified_publisher_not_pr_request(self):
    expected = PublishedReady(
      "refs/heads/PRELIM-issue-123/main-"+G,C,"ready-"+G)
    with (
      patch("repo_workflow.prelim_ready_recorded.publish_recorded_ready_certified",
        return_value=expected) as publish,
      patch("repo_workflow.prelim_integration.dispatch_configured") as legacy,
      patch("repo_workflow.prelim_integration._remote_ref",return_value=None),
    ):
      result=submit_ready_prelim(".",G,
        {"repository":{"authoritativeRemote":"origin"}},
        ticket=123,destination="main",request_id="ready-"+G,
        backend=object(),resolve_parent=lambda issue:"main")
    self.assertEqual(result,expected)
    self.assertEqual(publish.call_args.kwargs["destination"],"main")
    self.assertEqual(publish.call_args.kwargs["guid"],G)
    legacy.assert_not_called()

  def test_accepted_v2_identity_routes_directly_to_ready_ref(self):
    expected=PublishedReady(
      "refs/heads/PRELIM-issue-123/issue-100-"+G,C,"v2-ready")
    with (
      patch("repo_workflow.prelim_integration._remote_ref",
            return_value="f"*40),
      patch("repo_workflow.prelim_ready_v2_publish.publish_destination_prelim",
            return_value=expected) as qualified,
      patch("repo_workflow.prelim_ready_recorded.publish_recorded_ready_certified"
            ) as legacy,
    ):
      result=submit_ready_prelim(".",G,
        {"repository":{"authoritativeRemote":"origin"}},
        ticket=123,destination="issue-100",request_id="v2-ready",
        backend=object(),resolve_parent=lambda issue:"issue-100")
    self.assertEqual(result,expected)
    self.assertEqual(qualified.call_args.kwargs["destination"],"issue-100")
    legacy.assert_not_called()

  def test_non_main_destination_preserved(self):
    with (
      patch("repo_workflow.prelim_integration._remote_ref",return_value=None),
      patch(
      "repo_workflow.prelim_ready_recorded.publish_recorded_ready_certified",
      return_value=PublishedReady(
        "refs/heads/PRELIM-issue-123/issue-100-"+G,C,"request"),
      ) as publish,
    ):
      submit_ready_prelim(".",G,{"repository":{"authoritativeRemote":"origin"}},ticket=123,
        destination="issue-100",request_id="request",
        backend=object(),resolve_parent=lambda issue:"issue-100")
    self.assertEqual(publish.call_args.kwargs["destination"],"issue-100")


if __name__=="__main__":
  unittest.main()
