"""Independent provider-identity acceptance for READY PRELIM publication."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from repo_workflow.prelim_ready import ReadyPublicationError
from repo_workflow.prelim_ready_provider_scope import verify_ready_provider_scope


class Backend:
  repository = "Org/Repo"

  def __init__(self):
    self.actual = self.repository
    self.calls = []

  def get(self, path):
    assert path == ""
    self.calls.append(path)
    return {
      "full_name": self.actual,
      "clone_url": "https://github.com/Org/Repo.git",
      "ssh_url": "git@github.com:Org/Repo.git",
    }


class ProviderScopeTests(unittest.TestCase):
  def setUp(self):
    self.backend = Backend()
    self.fetch = "https://github.com/Org/Repo.git"
    self.push = self.fetch
    self.calls = []

  def git(self, root, *args, **kwargs):
    self.calls.append(args)
    if args == ("remote", "get-url", "origin"):
      return SimpleNamespace(returncode=0, stdout=self.fetch + "\n")
    if args == ("remote", "get-url", "--push", "origin"):
      return SimpleNamespace(returncode=0, stdout=self.push + "\n")
    self.fail("unexpected Git invocation")

  def verify(self):
    with patch("repo_workflow.prelim_ready_provider_scope.git",
               side_effect=self.git):
      return verify_ready_provider_scope(Path("."), "origin", self.backend)

  def test_provider_bound_read_and_mutation_urls(self):
    self.assertIsNone(self.verify())
    self.assertEqual(self.backend.calls, [""])
    self.assertEqual(len(self.calls), 2)

  def test_reported_ssh_url_accepted(self):
    self.fetch = self.push = "git@github.com:Org/Repo.git"
    self.assertIsNone(self.verify())

  def test_foreign_fetch_refused(self):
    self.fetch = self.push = "https://github.com/Org/Other.git"
    with self.assertRaises(ReadyPublicationError):
      self.verify()

  def test_mismatched_push_endpoint_refused(self):
    self.push = "https://github.com/Org/Other.git"
    with self.assertRaises(ReadyPublicationError):
      self.verify()

  def test_provider_identity_mismatch_refused(self):
    self.backend.actual = "Org/Other"
    with self.assertRaises(ReadyPublicationError):
      self.verify()
    self.assertEqual(self.calls, [])

  def test_unavailable_provider_response_refused(self):
    with patch.object(self.backend, "get",
                      side_effect=RuntimeError("unavailable")):
      with self.assertRaises(ReadyPublicationError):
        self.verify()


if __name__ == "__main__":
  unittest.main()
