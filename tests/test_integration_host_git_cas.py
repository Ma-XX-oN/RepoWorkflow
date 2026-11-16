"""Local two-writer immutable PRELIM publication and lost-ACK recovery."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters"))
from repo_workflow.prelim_submission import SubmissionError, publish_submission
from repo_workflow.prelim_queue import parse_ready_prelim

REF = "refs/heads/PRELIM-issue-123.0.1"


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

  def record(self, candidate):
    """Describe an immutable submission independently of mutable branch state."""
    ref = "refs/heads/PRELIM-issue-124.0.1"
    guid = parse_ready_prelim(ref, candidate).guid
    return {"repository":"Org/Repo", "guid":guid,
            "prelim_ref":ref,
            "source_sha":candidate, "candidate_sha":candidate, "parent_sha":self.a,
            "destination":"main", "version":"1.2.3-issue.124.0.1",
            "inputs_sha256":"f"*64, "release":"patch"}

  def test_only_one_competing_writer_can_publish_the_same_generation(self):
    first = self.record(self.b)
    publish_submission(self.one, first, remote="origin")
    with self.assertRaises(SubmissionError):
      publish_submission(self.two, self.record(self.c), remote="origin")
    observed = git(self.one, "ls-remote", "origin", first["prelim_ref"]).split()[0]
    self.assertEqual(observed, self.b)
    self.assertEqual(self.remote_sha(), self.a)

  def test_lost_ack_after_actual_provider_write_is_reconciled(self):
    original_run = subprocess.run
    def drop_push_ack(*args, **kwargs):
      result = original_run(*args, **kwargs)
      if "push" in args[0] and result.returncode == 0:
        return subprocess.CompletedProcess(args[0], 1, b"", b"ACK lost")
      return result
    with patch("subprocess.run", side_effect=drop_push_ack):
      result = publish_submission(self.one, self.record(self.b), remote="origin")
    self.assertEqual(result.sha, self.b)
    self.assertEqual(self.remote_sha(), self.a)

  def test_existing_prelim_without_receipt_requires_explicit_migration(self):
    record = self.record(self.a)
    record["prelim_ref"] = REF
    record["guid"] = parse_ready_prelim(REF, self.a).guid
    record["version"] = "1.2.3-issue.123.0.1"
    with self.assertRaisesRegex(SubmissionError, "missing provenance"):
      publish_submission(self.one, record, remote="origin")
    self.assertEqual(self.remote_sha(), self.a)

  def test_missing_object_is_rejected_without_push(self):
    with self.assertRaisesRegex(SubmissionError, "include"):
      publish_submission(self.one, self.record("d"*40), remote="origin")
    self.assertEqual(self.remote_sha(), self.a)


if __name__ == "__main__":
  unittest.main()
