"""Independent Git-provider contract checks for issue #82 PRELIM attempts."""

from concurrent.futures import ThreadPoolExecutor
import json
import uuid
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

  def test_conflict_resolution_produces_new_candidate(self):
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
    with self.assertRaises(PrelimError):
      self.construct()
    records = list((self.root / ".repoworkflow" / "state" /
                    "prelim" / "attempts").glob("*.json"))
    self.assertEqual(len(records), 1)
    attempt = json.loads(records[0].read_text())["value"]["attempt"]
    from repo_workflow.prelim_attempt import _workspace
    workspace = _workspace(self.root, attempt)
    (workspace / "VERSION").write_text("1.2.4\n")
    git(workspace, "add", "VERSION")
    completed = finish_prelim(self.root, attempt, self.config)
    self.assertEqual(completed.state, "ready")
    self.assertEqual(completed.proposed_version, "1.2.4")
    self.assertEqual(self.construct(attempt), completed)

  def test_rejects_reuse_with_different_release_intent(self):
    result = self.construct()
    with self.assertRaisesRegex(PrelimError, "parameters differ"):
      construct_prelim(self.root, "7", "refs/heads/issue-7",
                       self.config, bump="minor", attempt_id=result.attempt)

  def test_remote_candidate_rewrite_rejected(self):
    result = self.construct()
    git(self.root, "push", "origin", "+refs/heads/main:refs/heads/" + result.branch)
    with self.assertRaisesRegex(PrelimError, "remote candidate"):
      self.construct(result.attempt)

  def test_mismatched_remote_record_refuses_replay(self):
    result = self.construct()
    state_ref = f"refs/heads/prelim-state/{result.attempt}"
    git(self.root, "push", "origin", f":{state_ref}")
    # An absent state branch can be republished only from exact local state.
    self.assertEqual(self.construct(result.attempt), result)


  def test_zero_delta_source_keeps_version_only_candidate(self):
    # An accepted source already contained in authoritative main still
    # produces a versioned physical candidate without an empty merge.
    base = git(self.root, "rev-parse", "main").stdout.strip()
    git(self.root, "update-ref", "refs/heads/issue-7", base)
    lifecycle = LifecycleStore(self.root)
    old = lifecycle.read("7")
    reopened = lifecycle.transition("7", "reject/reopen", None, 0,
                                    self.writer, old.revision)
    review = lifecycle.transition("7", "submit-review", base, 0,
                                  self.writer, reopened.revision)
    lifecycle.transition("7", "accept", base, 0, self.writer,
                         review.revision)
    result = self.construct()
    self.assertEqual(result.proposed_version, "1.2.4")
    self.assertEqual(result.state, "ready")
    self.assertEqual(git(self.root, "rev-parse", "issue-7").stdout.strip(), base)

  def test_state_branch_republication_preserves_exact_commit(self):
    result = self.construct()
    ref = f"refs/heads/prelim-state/{result.attempt}"
    before = git(self.root, "rev-parse", ref).stdout.strip()
    git(self.root, "push", "origin", f":{ref}")
    self.assertEqual(self.construct(result.attempt), result)
    self.assertEqual(git(self.root, "rev-parse", ref).stdout.strip(), before)
    self.assertEqual(git(self.root, "ls-remote", "origin", ref).stdout.split()[0],
                     before)



  def test_concurrent_same_guid_has_one_immutable_result(self):
    attempt = str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=2) as workers:
      results = list(workers.map(self.construct, (attempt, attempt)))
    self.assertEqual(results[0], results[1])
    self.assertEqual(results[0].state, "ready")
    self.assertEqual(git(self.root, "rev-parse", results[0].branch).stdout.strip(),
                     results[0].candidate_sha)

  def test_abrupt_worker_death_releases_attempt_lock(self):
    from repo_workflow.prelim_attempt import _attempt_lock
    attempt = str(uuid.uuid4())
    script = (
      "import sys, time\n"
      "from pathlib import Path\n"
      "from repo_workflow.prelim_attempt import _attempt_lock\n"
      "from repo_workflow.state_store import durable_store\n"
      "root = Path(sys.argv[1])\n"
      "with _attempt_lock(root, durable_store(root), sys.argv[2]):\n"
      "  print('locked', flush=True)\n"
      "  time.sleep(60)\n"
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    worker = subprocess.Popen(
      [sys.executable, "-c", script, str(self.root), attempt],
      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
      text=True, env=environment,
    )
    try:
      self.assertEqual(worker.stdout.readline().strip(), "locked")
    finally:
      worker.kill()
      worker.communicate(timeout=10)
    with _attempt_lock(self.root, durable_store(self.root), attempt):
      pass



  def test_fresh_clone_restores_provider_attempt_exactly(self):
    original = self.construct()
    git(self.root, "push", "origin", "refs/heads/issue-7:refs/heads/issue-7")
    fresh = Path(self.temp.name) / "fresh"
    subprocess.run(["git", "clone", "-b", "main", str(self.remote),
                    str(fresh)], check=True, capture_output=True)
    git(fresh, "checkout", "-b", "issue-7", "origin/issue-7")
    restored = LifecycleStore(fresh)
    initial = restored.transition("7", "start", None, 0, self.writer, None)
    review = restored.transition("7", "submit-review", self.source, 0,
                                 self.writer, initial.revision)
    restored.transition("7", "accept", self.source, 0, self.writer,
                        review.revision)
    result = construct_prelim(fresh, "7", "refs/heads/issue-7",
                              self.config, attempt_id=original.attempt)
    self.assertEqual(result, original)
    self.assertEqual(git(fresh, "rev-parse", original.branch).stdout.strip(),
                     original.candidate_sha)



  def test_corrupt_local_identity_cannot_be_published(self):
    from repo_workflow.prelim_identity import PrelimIdentityError
    result = self.construct()
    key = f"prelim/attempts/{result.attempt}"
    path = durable_store(self.root)._path(key)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["value"]["source_ref"] = "refs/heads/issue-999"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with self.assertRaises(PrelimIdentityError):
      self.construct(result.attempt)

  def test_corrupt_attempt_schema_rejected(self):
    from repo_workflow.prelim_identity import PrelimIdentityError
    result = self.construct()
    key = f"prelim/attempts/{result.attempt}"
    path = durable_store(self.root)._path(key)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["value"]["candidate_sha"] = "not-a-sha"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with self.assertRaises(PrelimIdentityError):
      self.construct(result.attempt)



if __name__ == "__main__":
  unittest.main()
