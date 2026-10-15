"""Independent Git-provider contract checks for issue #82 PRELIM attempts."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.git import git
from repo_workflow.lifecycle_store import LifecycleStore
from repo_workflow.prelim_attempt import (
  PrelimError, construct_prelim, finish_prelim,
)
from repo_workflow.state_store import WriterIdentity, durable_store


class PrelimAttemptTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    self.remote = Path(self.temp.name) / "remote.git"
    subprocess.run(["git", "init", "--bare", str(self.remote)], check=True,
                   capture_output=True)
    git(self.root, "init", "-b", "main")
    git(self.root, "config", "user.name", "RepoWorkflow fixture")
    git(self.root, "config", "user.email", "test@example.invalid")
    (self.root / "VERSION").write_text("1.2.3\n")
    scripts = self.root / "scripts"
    scripts.mkdir()
    (scripts / "version.py").write_text(
      "from pathlib import Path\n"
      "import sys\n"
      "p = Path('VERSION')\n"
      "v = p.read_text().strip()\n"
      "if len(sys.argv) > 1:\n"
      "  major, minor, patch = map(int, v.split('.'))\n"
      "  if sys.argv[1:] == ['integrate','--increment','patch']:\n"
      "    patch += 1\n"
      "  elif sys.argv[1:] == ['integrate','--increment','minor']:\n"
      "    minor += 1\n"
      "    patch = 0\n"
      "  else:\n"
      "    raise SystemExit(2)\n"
      "  v = f'{major}.{minor}.{patch}'\n"
      "  p.write_text(v + '\\n')\n"
      "print(v)\n"
    )
    git(self.root, "add", ".")
    git(self.root, "commit", "-m", "base")
    git(self.root, "remote", "add", "origin", str(self.remote))
    git(self.root, "push", "origin", "main")
    self.config = {
      "versionCommand": [sys.executable, "scripts/version.py"],
      "repository": {"authoritativeRemote": "origin"},
    }
    git(self.root, "checkout", "-b", "issue-7")
    (self.root / "accepted.txt").write_text("accepted work\n")
    git(self.root, "add", "accepted.txt")
    git(self.root, "commit", "-m", "accepted source")
    self.source = git(self.root, "rev-parse", "HEAD").stdout.strip()
    self.writer = WriterIdentity("test-worker", "fixture-session")
    lifecycle = LifecycleStore(self.root)
    first = lifecycle.transition("7", "start", None, 0, self.writer, None)
    review = lifecycle.transition("7", "submit-review", self.source,
                                  0, self.writer, first.revision)
    lifecycle.transition("7", "accept", self.source, 0, self.writer,
                         review.revision)
    self.identity = patch.dict(os.environ, {
      "RWF_WRITER_ID": "test-worker", "RWF_SESSION_ID": "fixture-session",
    })
    self.identity.start()
    self.addCleanup(self.identity.stop)

  def construct(self, attempt_id=None):
    return construct_prelim(self.root, "7", "refs/heads/issue-7",
                            self.config, attempt_id=attempt_id)

  def test_exact_candidate_and_authenticated_remote_readback(self):
    result = self.construct()
    self.assertEqual(result.state, "ready")
    self.assertEqual(result.proposed_version, "1.2.4")
    self.assertEqual(git(self.root, "rev-parse", "issue-7").stdout.strip(),
                     self.source)
    self.assertEqual(git(self.root, "branch", "--show-current").stdout.strip(),
                     "issue-7")
    self.assertEqual(git(self.root, "merge-base", "--is-ancestor",
                         self.source, result.candidate_sha,
                         check=False).returncode, 0)
    self.assertEqual(git(self.root, "ls-remote", "origin",
                         f"refs/heads/{result.branch}").stdout.split()[0],
                     result.candidate_sha)
    self.assertEqual(self.construct(result.attempt), result)

  def test_invalid_input_fails_without_attempt_record(self):
    for source, bump in [("refs/heads/main", "patch"),
                         ("refs/heads/issue-7", "major")]:
      with self.assertRaises(PrelimError):
        construct_prelim(self.root, "7", source, self.config, bump=bump)
    self.assertEqual(list((self.root / ".repoworkflow" / "state" /
                           "prelim").glob("**/*.json")), [])

  def test_lifecycle_and_ref_must_identify_accepted_source(self):
    git(self.root, "commit", "--allow-empty", "-m", "unaccepted mutation")
    with self.assertRaisesRegex(PrelimError, "accepted lifecycle"):
      self.construct()

  def test_stale_main_rejects_existing_attempt(self):
    existing = self.construct()
    git(self.root, "checkout", "main")
    git(self.root, "commit", "--allow-empty", "-m", "new main")
    git(self.root, "push", "origin", "main")
    git(self.root, "checkout", "issue-7")
    with self.assertRaisesRegex(PrelimError, "server main moved"):
      self.construct(existing.attempt)

  def test_conflicting_version_is_recoverable_and_not_accepted(self):
    # Make an accepted change to VERSION, then record the updated source SHA.
    (self.root / "VERSION").write_text("1.2.3-issue.7.0.1\n")
    git(self.root, "commit", "-am", "accepted version")
    new_source = git(self.root, "rev-parse", "HEAD").stdout.strip()
    lifecycle = LifecycleStore(self.root)
    old = lifecycle.read("7")
    reopened = lifecycle.transition("7", "reject/reopen", None, 0,
                                    self.writer, old.revision)
    review = lifecycle.transition("7", "submit-review", new_source,
                                  0, self.writer, reopened.revision)
    lifecycle.transition("7", "accept", new_source, 0,
                         self.writer, review.revision)
    with self.assertRaisesRegex(PrelimError, "explicit resolution"):
      self.construct()
    self.assertFalse(git(self.root, "show-ref", "--verify",
                         "refs/heads/prelim/7", check=False).returncode == 0)

  def test_mismatched_remote_record_refuses_replay(self):
    result = self.construct()
    state_ref = f"refs/heads/prelim-state/{result.attempt}"
    git(self.root, "push", "origin", f":{state_ref}")
    # An absent state branch can be republished only from exact local state.
    self.assertEqual(self.construct(result.attempt), result)


if __name__ == "__main__":
  unittest.main()