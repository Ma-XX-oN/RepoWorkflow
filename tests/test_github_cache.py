"""Black-box local-Git origin resolution for provider-backed cache reuse."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.github_cache import hosted_cache_checker


class GithubCacheOriginTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.root = Path(self.tmp.name)
    subprocess.run(["git", "-C", str(self.root), "init", "-q"], check=True)

  def remote(self, url):
    subprocess.run(
      ["git", "-C", str(self.root), "remote", "add", "origin", url],
      check=True,
    )

  def test_https_and_ssh_remotes_enable_verified_stage_reuse(self):
    for url in (
      "https://github.com/Ma-XX-oN/RepoWorkflow.git",
      "git@github.com:Ma-XX-oN/RepoWorkflow.git",
    ):
      with self.subTest(remote=url):
        subprocess.run(
          ["git", "-C", str(self.root), "remote", "remove", "origin"],
          check=False, capture_output=True,
        )
        self.remote(url)
        with patch(
          "repo_workflow.github_cache.verify_hosted_stage",
          return_value=True,
        ) as verifier:
          callback = hosted_cache_checker(self.root, "GREEN")
          self.assertIsNotNone(callback)
          self.assertTrue(callback({"providerRunId": 123}))
          verifier.assert_called_once_with(
            {"providerRunId": 123},
            repo="Ma-XX-oN/RepoWorkflow",
            stage="GREEN-testing",
          )

  def test_missing_non_github_or_malformed_origin_fails_closed(self):
    self.assertIsNone(hosted_cache_checker(self.root, "GREEN"))
    for url in (
      "https://example.com/Ma-XX-oN/RepoWorkflow.git",
      "https://github.com.example.com/Ma-XX-oN/RepoWorkflow.git",
      "/tmp/local.git",
    ):
      with self.subTest(url=url):
        subprocess.run(
          ["git", "-C", str(self.root), "remote", "remove", "origin"],
          check=False, capture_output=True,
        )
        self.remote(url)
        self.assertIsNone(hosted_cache_checker(self.root, "GREEN"))

  def test_unsupported_stage_has_no_shared_group_reuse(self):
    self.remote("https://github.com/Ma-XX-oN/RepoWorkflow")
    self.assertIsNone(hosted_cache_checker(self.root, "RED"))
    self.assertIsNone(hosted_cache_checker(self.root, "integration"))


if __name__ == "__main__":
  unittest.main()
