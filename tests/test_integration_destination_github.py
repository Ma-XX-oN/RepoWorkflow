"""#681 exact-SHA provider policy read preserves absent versus empty semantics."""
import base64
import unittest

from adapters.repo_host_github_integration_destination import (
  DestinationProviderError, read_destination_snapshot,
)


SHA = "a"*40
SECOND = "b"*40


class NotFound(Exception):
  code = "not_found"


class Backend:
  repository = "Org/Repo"

  def __init__(self):
    self.sha = SHA
    self.second_read = None
    self.read_count = 0
    self.policy = None
    self.calls = []
    self.name = self.repository

  def get(self, route):
    self.calls.append(route)
    if route == "":
      return {"full_name": self.name}
    if route.startswith("git/ref/heads/"):
      self.read_count += 1
      sha = (self.second_read if self.read_count > 1
             and self.second_read is not None else self.sha)
      return {
        "ref": "refs/" + route.removeprefix("git/ref/"),
        "object": {"sha": sha, "type": "commit"},
      }
    if route.startswith("contents/"):
      if self.policy is None:
        raise NotFound()
      path = route.split("?ref=", 1)[0].removeprefix("contents/")
      return {
        "path": path, "type": "file", "encoding": "base64",
        "content": base64.b64encode(
          self.policy.encode("utf-8")).decode("ascii"),
      }
    raise AssertionError("unknown provider route " + route)


class DestinationSnapshotTests(unittest.TestCase):
  def setUp(self):
    self.backend = Backend()

  def read(self, destination="main"):
    return read_destination_snapshot(self.backend, destination)

  def test_absent_policy_means_no_additional_allow_filter(self):
    result = self.read()
    self.assertEqual(result, {
      "destination": "main", "ref": "refs/heads/main", "sha": SHA,
      "policy_present": False, "policy_text": None,
    })
    self.assertIn(
      "contents/.repoworkflow/allow-tickets/to-main?ref=" + SHA,
      self.backend.calls)

  def test_empty_file_is_distinct_from_absent(self):
    self.backend.policy = ""
    result = self.read()
    self.assertTrue(result["policy_present"])
    self.assertEqual(result["policy_text"], "")

  def test_explicit_ticket_lines_are_returned_unchanged(self):
    self.backend.policy = "7\n12\n"
    result = self.read("issue-100")
    self.assertEqual(result["policy_text"], "7\n12\n")
    self.assertEqual(result["ref"], "refs/heads/issue-100")
    self.assertIn("to-issue-100?ref=" + SHA, self.backend.calls[-2])

  def test_tip_changes_during_policy_read_refuses_mixed_snapshot(self):
    self.backend.second_read = SECOND
    with self.assertRaisesRegex(DestinationProviderError, "changed"):
      self.read()

  def test_wrong_repository_does_not_read_branch(self):
    self.backend.name = "Org/Other"
    with self.assertRaisesRegex(DestinationProviderError, "repository"):
      self.read()
    self.assertEqual(self.backend.calls, [""])

  def test_invalid_destination_is_denied_before_provider(self):
    for branch in ("", "../main", "issue//100", "-option", "bad space"):
      with self.subTest(branch=branch):
        with self.assertRaises(DestinationProviderError):
          self.read(branch)
    self.assertEqual(self.backend.calls, [])

  def test_unreadable_or_corrupt_policy_is_not_absent(self):
    original = self.backend.get
    def malformed(route):
      value = original(route)
      if route.startswith("contents/"):
        value["content"] = "!not base64!"
      return value
    self.backend.policy = "7\n"
    self.backend.get = malformed
    with self.assertRaisesRegex(DestinationProviderError, "encoding"):
      self.read()

  def test_transport_failure_does_not_mean_missing_policy(self):
    original = self.backend.get
    def inaccessible(route):
      if route.startswith("contents/"):
        raise RuntimeError("provider outage")
      return original(route)
    self.backend.get = inaccessible
    with self.assertRaisesRegex(DestinationProviderError, "UNKNOWN"):
      self.read()


if __name__ == "__main__":
  unittest.main()
