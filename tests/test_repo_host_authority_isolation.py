"""Independent #80 host-authority verifier cannot come from mutable project."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters"))
from repo_host_github_authority import verifier_command


class HostAuthorityIsolationTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.project = Path(self.temp.name) / "project"
    self.project.mkdir()
    self.issuer = Path(self.temp.name) / "independent-verifier"
    self.issuer.write_text("issuer\n", encoding="utf-8")

  def configured(self, filename):
    with patch.dict(os.environ, {
        "RWF_REPO_HOST_AUTH_COMMAND": json.dumps([str(filename)])},
        clear=True):
      with patch("repo_host_github_authority.Path.cwd",
                 return_value=self.project):
        return verifier_command()

  def test_independent_absolute_external_verifier_retained(self):
    self.assertEqual(self.configured(self.issuer), [str(self.issuer)])

  def test_mutable_project_verifier_denied(self):
    self.assertIsNone(self.configured(self.project / "issuer"))

  def test_project_lexical_symlink_escape_denied(self):
    linked = self.project / "issuer-link"
    real_resolve = Path.resolve
    def redirected(path, *args, **kwargs):
      if path == linked:
        return self.issuer
      return real_resolve(path, *args, **kwargs)
    with patch("repo_host_github_authority.Path.resolve",
               autospec=True, side_effect=redirected):
      self.assertIsNone(self.configured(linked))

  def test_no_unconfigured_or_relative_authority(self):
    with patch.dict(os.environ, {}, clear=True):
      self.assertIsNone(verifier_command())
    self.assertIsNone(self.configured("relative-verifier"))


if __name__ == "__main__":
  unittest.main()
