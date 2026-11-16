"""Exercise the actual CI dispatch transport without sending a provider request."""
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from adapters.repo_host_github_provider import ProviderError
from repo_workflow.done_workflow import dispatch_done


class DoneDispatchTests(unittest.TestCase):
  """Dispatch is submission, including the provider's empty success response."""

  def test_empty_success_response_records_submission_only(self):
    """A successful empty HTTP response does not become a false UNKNOWN or DONE."""
    plan = {"repository": "Org/Repo", "prelim_ref": "refs/heads/PRELIM-issue-51.0.2"}
    with patch("adapters.repo_host_github_provider.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "", "")) as request:
      result = dispatch_done(Path.cwd(), plan)
    self.assertEqual(result["status"], "submitted")
    argv = request.call_args.args[0]
    self.assertIn("repos/Org/Repo/actions/workflows/prelim-done.yml/dispatches", argv)
    payload = json.loads(request.call_args.kwargs["input"])
    self.assertEqual(payload, {"ref": "PRELIM-issue-51.0.2",
      "inputs": {"prelim_ref": plan["prelim_ref"]}})

  def test_failed_dispatch_never_claims_submission(self):
    """Provider failure remains a failure rather than successful submission."""
    with patch("adapters.repo_host_github_provider.subprocess.run",
        return_value=subprocess.CompletedProcess([], 1, "", "HTTP 403")):
      with self.assertRaises(ProviderError):
        dispatch_done(Path.cwd(), {"repository": "Org/Repo",
          "prelim_ref": "refs/heads/PRELIM-issue-51.0.2"})
