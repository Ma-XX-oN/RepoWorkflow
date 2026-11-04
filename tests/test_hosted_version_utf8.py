"""Strict UTF-8 Git protocol coverage for hosted invocation identity."""
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from repo_workflow.hosted_version_identity import HostedVersionError, _git


class HostedVersionUtf8Tests(unittest.TestCase):
  def test_valid_utf8_is_decoded_independently_of_host_locale(self):
    raw = "→ 東京\n".encode("utf-8")
    result = subprocess.CompletedProcess(["git"], 0, raw, b"")
    with patch("repo_workflow.hosted_version_identity.git_bytes",
               return_value=result) as execute:
      self.assertEqual(_git(Path("."), "show", "HEAD:.ci/run"), "→ 東京\n")
    execute.assert_called_once_with(Path("."), "show", "HEAD:.ci/run",
                                    check=False)

  def test_invalid_utf8_is_rejected_not_replaced(self):
    result = subprocess.CompletedProcess(["git"], 0, b"invalid-\xff\n", b"")
    with patch("repo_workflow.hosted_version_identity.git_bytes",
               return_value=result):
      with self.assertRaisesRegex(HostedVersionError, "cannot decode hosted Git request"):
        _git(Path("."), "show", "HEAD:.ci/run")

  def test_nonzero_git_return_is_rejected(self):
    result = subprocess.CompletedProcess(["git"], 128, b"", b"missing")
    with patch("repo_workflow.hosted_version_identity.git_bytes",
               return_value=result):
      with self.assertRaisesRegex(HostedVersionError, "cannot verify hosted Git request"):
        _git(Path("."), "show", "missing")

  def test_git_invocation_exception_is_fail_closed(self):
    from repo_workflow.git import GitError
    with patch("repo_workflow.hosted_version_identity.git_bytes",
               side_effect=GitError("provider missing")):
      with self.assertRaisesRegex(HostedVersionError, "cannot decode hosted Git request"):
        _git(Path("."), "show", "HEAD:.ci/run")


if __name__ == "__main__":
  unittest.main()
