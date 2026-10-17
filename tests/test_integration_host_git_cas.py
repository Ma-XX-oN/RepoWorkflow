"""Local two-writer Git-protocol INT-ATTEMPT CAS acceptance."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters"))
from repo_host_github_integration import (
  IntegrationProviderError, cas_int_attempt_git,
)

REF = ("refs/heads/INT-ATTEMPT-issue-123/main-"
       "11111111-1111-4111-8111-111111111111")


def git(root, *args):
  p = subprocess.run(["git", "-C", str(root), *args],
    text=True, capture_output=True, check=True)
  return p.stdout.strip()


class GitCasTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    root = Path(self.tmp.name)
    self.remote = root / "remote.git"
    subprocess.run(["git", "init", "--bare", str(self.remote)],
      capture_output=True, check=True)
    self.one = root / "worker1"
    subprocess.run(["git", "init", "-b", "main", str(self.one)],
      capture_output=True, check=True)
    git(self.one, "config", "user.name", "RWF CAS Fixture")
    git(self.one, "config", "user.email", "cas@example.invalid")
    (self.one / "file").write_text("A\n")
    git(self.one, "add", "file")
    git(self.one, "commit", "-m", "A")
    self.a = git(self.one, "rev-parse", "HEAD")
    git(self.one, "remote", "add", "origin", str(self.remote))
    git(self.one, "push", "origin", "main")
    git(self.one, "push", "origin", self.a + ":" + REF)
    self.two = root / "worker2"
    subprocess.run(["git", "clone", "-b", "main",
                    str(self.remote), str(self.two)],
      capture_output=True, check=True)
    git(self.two, "config", "user.name", "RWF CAS Fixture")
    git(self.two, "config", "user.email", "cas@example.invalid")
    (self.one / "file").write_text("B\n")
    git(self.one, "add", "file")
    git(self.one, "commit", "-m", "B")
    self.b = git(self.one, "rev-parse", "HEAD")
    (self.two / "file").write_text("C\n")
    git(self.two, "add", "file")
    git(self.two, "commit", "-m", "C")
    self.c = git(self.two, "rev-parse", "HEAD")

  def remote_sha(self):
    return git(self.one, "ls-remote", "origin", REF).split()[0]

  def test_only_one_competing_writer_can_advance(self):
    result = cas_int_attempt_git(self.one, "origin", REF, self.a, self.b)
    self.assertEqual(result["sha"], self.b)
    with self.assertRaisesRegex(IntegrationProviderError, "CAS"):
      cas_int_attempt_git(self.two, "origin", REF, self.a, self.c)
    self.assertEqual(self.remote_sha(), self.b)

  def test_prelim_update_is_forbidden(self):
    with self.assertRaisesRegex(IntegrationProviderError, "invalid"):
      cas_int_attempt_git(self.one, "origin",
        REF.replace("INT-ATTEMPT", "PRELIM"), self.a, self.b)
    self.assertEqual(self.remote_sha(), self.a)

  def test_missing_object_is_rejected_without_push(self):
    with self.assertRaisesRegex(IntegrationProviderError, "unavailable"):
      cas_int_attempt_git(self.one, "origin", REF, self.a, "d"*40)
    self.assertEqual(self.remote_sha(), self.a)


if __name__ == "__main__":
  unittest.main()
