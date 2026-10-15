"""Real two-clone Git-provider tests for #83 stale PRELIM integration."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import unittest
import uuid

from repo_workflow.git import git
from repo_workflow.prelim_attempt import _workspace
from repo_workflow.prelim_reintegrate import (
  ReintegrationError, finish_reintegration, reintegrate_prelim,
)
from repo_workflow.state_store import durable_store
from tests.test_prelim_attempt import PrelimAttemptTests


class StalePrelimTests(unittest.TestCase):
  def setUp(self):
    # Reuse the independently certified #82 fixture and its cleanup stack;
    # exercise actual Git objects, real bare provider refs and lifecycle CAS.
    fixture = PrelimAttemptTests("test_exact_candidate_and_authenticated_remote_readback")
    fixture.setUp()
    self.addCleanup(fixture.doCleanups)
    self.fixture = fixture
    self.root = fixture.root
    self.remote = fixture.remote
    self.config = fixture.config
    self.previous = fixture.construct()
    self.base = git(self.root, "rev-parse", "main").stdout.strip()
    self.source = git(self.root, "rev-parse", "issue-7").stdout.strip()

  def advance(self, content="new main\n", filename="server-only.txt"):
    other = self.root.parent / ("writer-" + str(uuid.uuid4()))
    git(self.root, "clone", "--branch", "main", str(self.remote), str(other))
    git(other, "config", "user.name", "server writer")
    git(other, "config", "user.email", "writer@example.invalid")
    (other / filename).write_text(content)
    git(other, "add", ".")
    git(other, "commit", "-m", "advance server main")
    result = git(other, "rev-parse", "HEAD").stdout.strip()
    git(other, "push", "origin", "main")
    return result

  def reintegrate(self, guid=None):
    return reintegrate_prelim(
      self.root, self.previous.attempt, self.config, attempt_id=guid,
    )

  def test_exact_new_physical_candidate_preserves_old_resolution_and_source(self):
    newbase = self.advance()
    result = self.reintegrate()
    self.assertEqual(result.state, "ready")
    self.assertNotEqual(result.guid, self.previous.attempt)
    self.assertNotEqual(result.candidate, self.previous.candidate_sha)
    self.assertEqual(result.base, newbase)
    self.assertEqual(git(self.root, "rev-parse", "main").stdout.strip(), self.base)
    self.assertEqual(git(self.root, "rev-parse", "issue-7").stdout.strip(), self.source)
    for ancestor in (newbase, self.previous.candidate_sha, self.source):
      self.assertEqual(git(self.root, "merge-base", "--is-ancestor", ancestor,
                           result.candidate, check=False).returncode, 0)
    self.assertEqual(self.reintegrate(result.guid), result)
    state = durable_store(self.root).read("prelim/reintegrations/" + result.guid)
    self.assertEqual(state["value"]["inherited_evidence"], False)
    self.assertEqual(state["value"]["fresh_validation_required"], True)
    self.assertEqual(state["value"]["previous_candidate"], self.previous.candidate_sha)
    self.assertEqual(git(self.root, "ls-remote", "origin",
                         "refs/heads/" + result.branch).stdout.split()[0],
                     result.candidate)

  def test_no_main_change_is_rejected_without_record(self):
    guid = str(uuid.uuid4())
    with self.assertRaisesRegex(ReintegrationError, "has not advanced"):
      self.reintegrate(guid)
    self.assertFalse(durable_store(self.root)._path(
      "prelim/reintegrations/" + guid).exists())

  def test_changed_main_invalidates_completed_reintegration(self):
    self.advance()
    first = self.reintegrate()
    self.advance("another change\n", "more.txt")
    with self.assertRaisesRegex(ReintegrationError, "main moved again"):
      self.reintegrate(first.guid)
    again = self.reintegrate()
    self.assertNotEqual(first.guid, again.guid)
    self.assertNotEqual(first.candidate, again.candidate)

  def test_merge_conflict_requires_resolve_and_new_commit(self):
    self.advance("1.2.5\n", "VERSION")
    guid = str(uuid.uuid4())
    with self.assertRaisesRegex(ReintegrationError, "conflicts need explicit"):
      self.reintegrate(guid)
    self.assertEqual(durable_store(self.root).read(
      "prelim/reintegrations/" + guid)["value"]["state"], "conflict")
    worktree = _workspace(self.root, "reintegration-" + guid)
    (worktree / "VERSION").write_text("1.2.6\n")
    git(worktree, "add", "VERSION")
    result = finish_reintegration(self.root, guid, self.config)
    self.assertEqual(result.state, "ready")
    self.assertEqual(self.reintegrate(guid), result)

  def test_replaced_prior_candidate_is_rejected(self):
    self.advance()
    git(self.root, "push", "origin",
        "+refs/heads/main:refs/heads/" + self.previous.branch)
    with self.assertRaisesRegex(ReintegrationError, "old PRELIM candidate"):
      self.reintegrate()

  def test_same_guid_replay_and_distinct_parallel_attempts(self):
    self.advance()
    ids = [str(uuid.uuid4()) for _ in range(3)]
    with ThreadPoolExecutor(max_workers=3) as pool:
      results = list(pool.map(self.reintegrate, ids))
    self.assertEqual(len({r.candidate for r in results}), 3)
    self.assertEqual(len({r.guid for r in results}), 3)
    same = str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
      repeats = list(pool.map(self.reintegrate, (same, same)))
    self.assertEqual(repeats[0], repeats[1])

  def test_old_record_and_old_remote_ref_are_immutable(self):
    self.advance()
    key = "prelim/attempts/" + self.previous.attempt
    original = durable_store(self.root).read(key)
    ref = "refs/heads/" + self.previous.branch
    old_ref = git(self.root, "ls-remote", "origin", ref).stdout.strip()
    self.reintegrate()
    self.assertEqual(durable_store(self.root).read(key), original)
    self.assertEqual(git(self.root, "ls-remote", "origin", ref).stdout.strip(),
                     old_ref)

  def test_rejects_attempt_that_inherits_green_or_prelim_evidence(self):
    self.advance()
    result = self.reintegrate()
    store = durable_store(self.root)
    path = store._path("prelim/reintegrations/" + result.guid)
    record = json.loads(path.read_text())
    record["value"]["inherited_evidence"] = True
    path.write_text(json.dumps(record))
    with self.assertRaisesRegex(ReintegrationError, "cannot be inherited"):
      self.reintegrate(result.guid)

  def test_remote_state_rewrite_fails_closed(self):
    self.advance()
    result = self.reintegrate()
    ref = "refs/heads/prelim-reintegration-state/" + result.guid
    git(self.root, "push", "origin", "+refs/heads/main:" + ref)
    with self.assertRaisesRegex(ReintegrationError, "remote state"):
      self.reintegrate(result.guid)


if __name__ == "__main__":
  unittest.main()
