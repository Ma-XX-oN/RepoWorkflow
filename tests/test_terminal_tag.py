"""Real-Git contract tests for immutable regression/integration result tags."""

from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest
import sys
from unittest.mock import patch

from repo_workflow import terminal_tag

from repo_workflow.terminal_tag import TerminalTagError, publish_terminal_tag

VERSION = "0.1.121-issue.545.0.1"

class TerminalTagTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    base = Path(self.temp.name)
    self.root = base / "work"
    self.remote = base / "remote.git"
    self.git_in(base, "init", "--bare", str(self.remote))
    self.git_in(base, "init", "-b", "issue-545-test", str(self.root))
    self.git("config", "user.name", "Test")
    self.git("config", "user.email", "test@example.invalid")
    (self.root / "source.txt").write_text("original source\n")
    self.git("add", "source.txt")
    self.git("commit", "-m", "candidate")
    self.candidate = self.git("rev-parse", "HEAD")
    self.git("remote", "add", "origin", str(self.remote))
    self.git("push", "origin", "HEAD:refs/heads/issue-545-test")
    self.log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    self.log.parent.mkdir(parents=True, exist_ok=True)

  def git_in(self, cwd, *args):
    result = subprocess.run(
      ["git", *args], cwd=cwd, text=True, capture_output=True, check=False,
    )
    if result.returncode:
      raise AssertionError(result.stderr)
    return result.stdout.strip()

  def git(self, *args):
    return self.git_in(self.root, *args)

  def issue_marker(self):
    path = self.root / ".ci/run"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("regression-testing " + self.git("rev-parse", "HEAD") + "\n")
    self.git("add", ".ci/run")
    self.git("commit", "-m", "dedicated CI request")

  def published(self, tag):
    result = self.git(
      "ls-remote", "--tags", "origin",
      "refs/tags/" + tag, "refs/tags/" + tag + "^{}",
    )
    return dict(
      (line.split("\t", 1)[1], line.split("\t", 1)[0])
      for line in result.splitlines() if "\t" in line
    )

  def issue_tag(self, outcome, **overrides):
    args = {
      "stage": "regression", "remote": "origin", "version": VERSION,
      "candidate": self.candidate, "outcome": outcome,
      "canonical_log": self.log,
    }
    args.update(overrides)
    evidence = {
      "kind": args["stage"], "testVersion": args["version"],
      "branch": "issue-545-test",
      "testSHA": args["candidate"],
      "result": {"PASS": "succeeded", "FAIL": "failed",
                 "INCOMPLETE": "incomplete"}.get(outcome, "incomplete"),
      "reusable": True, "headChangedDuringTest": False,
      "uncommittedChanges": [],
    }
    if not self.log.exists():
      self.log.write_text(json.dumps(evidence) + "\n")
    else:
      records = [json.loads(line) for line in self.log.read_text().splitlines()]
      if not any(row.get("testVersion") == args["version"] for row in records):
        with self.log.open("a") as handle:
          handle.write(json.dumps(evidence) + "\n")
    return publish_terminal_tag(self.root, **args)

  def test_pass_tag_targets_original_commit_before_multiple_requests(self):
    self.issue_marker()
    self.issue_marker()
    latest = self.git("rev-parse", "HEAD")
    tag = self.issue_tag("PASS")
    self.assertEqual(tag, "v" + VERSION)
    self.assertEqual(
      self.git("rev-parse", "refs/tags/" + tag + "^{commit}"), self.candidate)
    self.assertNotEqual(latest, self.candidate)
    self.assertEqual(
      self.published(tag)["refs/tags/" + tag + "^{}"], self.candidate)

  def test_local_only_tag_then_remote_publication_reuses_same_object(self):
    tag = self.issue_tag("PASS", push=False)
    local_ref = self.git("rev-parse", "refs/tags/" + tag)
    self.assertEqual(self.published(tag), {})
    self.assertEqual(self.issue_tag("PASS", push=False), tag)
    self.assertEqual(self.git("rev-parse", "refs/tags/" + tag), local_ref)
    self.assertEqual(self.issue_tag("PASS", push=True), tag)
    self.assertEqual(self.git("rev-parse", "refs/tags/" + tag), local_ref)
    self.assertEqual(
      self.published(tag)["refs/tags/" + tag + "^{}"], self.candidate)

  def test_repeating_same_outcome_is_idempotent(self):
    tag = self.issue_tag("PASS")
    first = self.git("rev-parse", "refs/tags/" + tag)
    self.assertEqual(self.issue_tag("PASS"), tag)
    self.assertEqual(self.git("rev-parse", "refs/tags/" + tag), first)

  def test_complete_failure_tag_points_to_candidate(self):
    tag = self.issue_tag("FAIL")
    self.assertEqual(tag, "v" + VERSION + "-CI-FAIL")
    self.assertEqual(
      self.published(tag)["refs/tags/" + tag + "^{}"], self.candidate)

  def test_missing_canonical_evidence_blocks_publication(self):
    with self.assertRaisesRegex(TerminalTagError, "unavailable"):
      publish_terminal_tag(
        self.root, stage="regression", remote="origin",
        version=VERSION, candidate=self.candidate, outcome="PASS",
        canonical_log=self.log,
      )
    self.assertEqual(self.git("tag", "--list"), "")

  def test_wrong_issue_results_file_cannot_certify_version(self):
    other = self.log.with_name("testResults-546.jsonl")
    other.write_text(json.dumps({
      "kind": "regression", "branch": "issue-545-test",
      "testVersion": VERSION, "testSHA": self.candidate,
      "result": "succeeded", "reusable": True,
      "headChangedDuringTest": False, "uncommittedChanges": [],
    }) + "\n")
    with self.assertRaisesRegex(TerminalTagError, "issue differs"):
      publish_terminal_tag(
        self.root, stage="regression", remote="origin",
        version=VERSION, candidate=self.candidate, outcome="PASS",
        canonical_log=other,
      )
    self.assertEqual(self.git("tag", "--list"), "")

  def test_external_lookalike_log_is_rejected(self):
    external = self.root.parent / "testResults-545.jsonl"
    external.write_text(json.dumps({
      "kind": "regression", "branch": "issue-545-test",
      "testVersion": VERSION, "testSHA": self.candidate,
      "result": "succeeded", "reusable": True,
      "headChangedDuringTest": False, "uncommittedChanges": [],
    }) + "\n")
    with self.assertRaisesRegex(TerminalTagError, "validation path"):
      publish_terminal_tag(
        self.root, stage="regression", remote="origin",
        version=VERSION, candidate=self.candidate, outcome="PASS",
        canonical_log=external,
      )

  def test_wrong_issue_branch_in_record_is_rejected(self):
    self.log.write_text(json.dumps({
      "kind": "regression", "branch": "issue-546-other",
      "testVersion": VERSION, "testSHA": self.candidate,
      "result": "succeeded", "reusable": True,
      "headChangedDuringTest": False, "uncommittedChanges": [],
    }) + "\n")
    with self.assertRaisesRegex(TerminalTagError, "branch differs"):
      self.issue_tag("PASS")
    self.assertEqual(self.git("tag", "--list"), "")

  def test_cross_phase_version_reuse_is_rejected(self):
    self.issue_tag("PASS")
    with self.assertRaisesRegex(TerminalTagError, "another phase"):
      self.issue_tag("PASS", stage="integration")
    self.assertEqual(len(self.git("tag", "--list").splitlines()), 1)

  def test_false_pass_without_success_evidence_is_rejected(self):
    self.issue_tag("FAIL")
    with self.assertRaisesRegex(TerminalTagError, "outcome"):
      self.issue_tag("PASS")

  def test_genuine_failure_not_reusable_still_receives_failure_tag(self):
    self.log.write_text(json.dumps({
      "kind": "regression", "testVersion": VERSION,
      "branch": "issue-545-test",
      "testSHA": self.candidate, "result": "failed",
      "reusable": False, "headChangedDuringTest": False,
      "uncommittedChanges": [],
    }) + "\n")
    self.assertEqual(self.issue_tag("FAIL"), "v" + VERSION + "-CI-FAIL")

  def test_nonreusable_pass_cannot_receive_tag(self):
    self.log.write_text(json.dumps({
      "kind": "regression", "testVersion": VERSION,
      "branch": "issue-545-test",
      "testSHA": self.candidate, "result": "succeeded",
      "reusable": False, "headChangedDuringTest": False,
      "uncommittedChanges": [],
    }) + "\n")
    with self.assertRaisesRegex(TerminalTagError, "does not establish"):
      self.issue_tag("PASS")
    self.assertEqual(self.git("tag", "--list"), "")

  def test_incomplete_retry_before_pass_does_not_consume_version(self):
    entries = [
      {"kind": "regression", "testVersion": VERSION,
       "branch": "issue-545-test",
       "testSHA": self.candidate, "result": result,
       "reusable": result == "succeeded",
       "headChangedDuringTest": False, "uncommittedChanges": []}
      for result in ("incomplete", "succeeded")
    ]
    self.log.write_text(
      "\n".join(json.dumps(item) for item in entries) + "\n",
    )
    tag = self.issue_tag("PASS")
    self.assertEqual(
      self.published(tag)["refs/tags/" + tag + "^{}"], self.candidate)

  def test_conflicting_results_for_same_version_are_rejected(self):
    self.issue_tag("INCOMPLETE")
    self.log.write_text("\n".join(json.dumps({
      "kind": "regression", "testVersion": VERSION,
      "branch": "issue-545-test",
      "testSHA": self.candidate, "result": result,
      "reusable": True, "headChangedDuringTest": False,
      "uncommittedChanges": [],
    }) for result in ("succeeded", "failed")) + "\n")
    with self.assertRaisesRegex(TerminalTagError, "conflicting"):
      self.issue_tag("PASS")
    self.assertEqual(self.git("tag", "--list"), "")

  def test_invalid_canonical_record_blocks_publication(self):
    for payload in (b"{bad json\n", b"\xff"):
      with self.subTest(payload=payload):
        self.log.write_bytes(payload)
        with self.assertRaisesRegex(TerminalTagError, "malformed"):
          publish_terminal_tag(
            self.root, stage="integration", remote="origin",
            version=VERSION, candidate=self.candidate,
            outcome="PASS", canonical_log=self.log,
          )

  def test_incomplete_never_creates_a_tag(self):
    self.assertIsNone(self.issue_tag("INCOMPLETE"))
    self.assertEqual(self.git("tag", "--list"), "")

  def test_opposite_outcome_cannot_be_published(self):
    self.issue_tag("FAIL")
    with self.assertRaisesRegex(TerminalTagError, "outcome|opposite"):
      self.issue_tag("PASS")

  def test_non_terminal_test_stages_never_publish_tags(self):
    for stage in ("RED", "temporary", "GREEN", "results"):
      with self.subTest(stage=stage):
        with self.assertRaisesRegex(TerminalTagError, "regression or integration"):
          self.issue_tag("PASS", stage=stage)
    self.assertEqual(self.git("tag", "--list"), "")

  def test_malformed_version_or_candidate_fails_without_tag(self):
    with self.assertRaisesRegex(TerminalTagError, "development version"):
      self.issue_tag("PASS", version="0.1.121")
    with self.assertRaisesRegex(TerminalTagError, "full original candidate"):
      self.issue_tag("FAIL", candidate="abc")
    with self.assertRaisesRegex(TerminalTagError, "unknown terminal"):
      self.issue_tag("SKIPPED")
    self.assertEqual(self.git("tag", "--list"), "")

  def test_well_formed_but_nonexistent_candidate_cannot_be_tagged(self):
    with self.assertRaises(TerminalTagError):
      self.issue_tag("PASS", candidate="f" * 40)
    self.assertEqual(self.git("tag", "--list"), "")

  def test_remote_lightweight_tag_is_not_accepted_as_terminal_evidence(self):
    tag = "v" + VERSION
    self.git("tag", tag, self.candidate)
    self.git("push", "origin", "refs/tags/" + tag)
    self.git("tag", "-d", tag)
    with self.assertRaisesRegex(TerminalTagError, "not annotated"):
      self.issue_tag("PASS")

  def test_existing_remote_different_target_is_rejected(self):
    self.issue_marker()
    self.git("tag", "-a", "v" + VERSION, "HEAD", "-m", "conflict")
    self.git("push", "origin", "refs/tags/v" + VERSION)
    with self.assertRaisesRegex(TerminalTagError, "different commit"):
      self.issue_tag("PASS")

  def test_unannotated_terminal_tag_is_rejected(self):
    self.git("tag", "v" + VERSION, self.candidate)
    with self.assertRaisesRegex(TerminalTagError, "annotated"):
      self.issue_tag("PASS")

  def test_local_replay_after_remote_publication(self):
    tag = self.issue_tag("PASS")
    self.git("tag", "-d", tag)
    self.assertEqual(self.issue_tag("PASS"), tag)
    self.assertEqual(
      self.published(tag)["refs/tags/" + tag + "^{}"], self.candidate)

  def test_successive_phase_versions_preserve_both_exact_targets(self):
    first_tag = self.issue_tag("PASS")
    first_sha = self.candidate
    (self.root / "source.txt").write_text("integration revision\n")
    self.git("add", "source.txt")
    self.git("commit", "-m", "prepare next versioned phase candidate")
    second_sha = self.git("rev-parse", "HEAD")
    self.candidate = second_sha
    second_tag = self.issue_tag(
      "PASS", stage="integration", version="0.1.121-issue.545.0.2",
    )
    self.assertNotEqual(first_tag, second_tag)
    self.assertEqual(
      self.published(first_tag)["refs/tags/" + first_tag + "^{}"], first_sha,
    )
    self.assertEqual(
      self.published(second_tag)["refs/tags/" + second_tag + "^{}"],
      second_sha,
    )

  def test_concurrent_identical_publication_is_idempotent(self):
    actual_git = terminal_tag._git

    def concurrent_push(root, *args, **kw):
      if args and args[0] == "push":
        # Model a second publisher winning the remote push just before ours.
        actual_git(root, *args, check=True)
        return subprocess.CompletedProcess(args, 1, "", "already published")
      return actual_git(root, *args, **kw)

    with patch("repo_workflow.terminal_tag._git", side_effect=concurrent_push):
      tag = self.issue_tag("PASS")
    self.assertEqual(
      self.published(tag)["refs/tags/" + tag + "^{}"], self.candidate)

  def test_failed_push_can_retry_without_moving_local_tag(self):
    actual_git = terminal_tag._git

    def failed_push(root, *args, **kw):
      if args and args[0] == "push":
        return subprocess.CompletedProcess(args, 1, "", "network interruption")
      return actual_git(root, *args, **kw)

    with patch("repo_workflow.terminal_tag._git", side_effect=failed_push):
      with self.assertRaisesRegex(TerminalTagError, "publication failed"):
        self.issue_tag("PASS")
    tag = "v" + VERSION
    first = self.git("rev-parse", "refs/tags/" + tag)
    self.assertEqual(self.issue_tag("PASS"), tag)
    self.assertEqual(self.git("rev-parse", "refs/tags/" + tag), first)
    self.assertEqual(
      self.published(tag)["refs/tags/" + tag + "^{}"], self.candidate)

  def test_local_only_publish_requires_no_network_or_remote(self):
    tag = self.issue_tag("PASS", remote="not-a-remote", push=False)
    self.assertEqual(tag, "v" + VERSION)
    self.assertEqual(
      self.git("rev-parse", "refs/tags/" + tag + "^{commit}"), self.candidate)
    self.assertEqual(self.published(tag), {})

  def test_unreachable_remote_does_not_create_local_tag(self):
    with self.assertRaises(TerminalTagError):
      self.issue_tag("PASS", remote="not-a-remote")
    self.assertEqual(self.git("tag", "--list"), "")

  def seed_success_log(self):
    self.log.write_text(json.dumps({
      "kind": "regression", "testVersion": VERSION,
      "branch": "issue-545-test", "testSHA": self.candidate,
      "result": "succeeded", "reusable": True,
      "headChangedDuringTest": False, "uncommittedChanges": [],
    }) + "\n", encoding="utf-8")

  def test_aliased_repository_root_and_real_log_are_accepted(self):
    alias = self.root.parent / "aliased-work"
    try:
      alias.symlink_to(self.root, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
      self.skipTest("directory symlink unavailable: " + str(error))
    self.seed_success_log()
    common = {
      "stage": "regression", "remote": "origin",
      "version": VERSION, "candidate": self.candidate,
      "outcome": "PASS", "push": False,
    }
    aliased_log = alias / ".repoworkflow/validation" / self.log.name
    tag = publish_terminal_tag(alias, canonical_log=aliased_log, **common)
    self.assertEqual(tag, "v" + VERSION)
    self.assertEqual(self.git("cat-file", "-t", "refs/tags/" + tag), "tag")
    self.assertEqual(
      publish_terminal_tag(alias, canonical_log=self.log, **common), tag,
    )
    self.assertEqual(
      self.git("rev-parse", "refs/tags/" + tag + "^{commit}"), self.candidate)

  def test_symlinked_validation_directory_outside_repository_is_rejected(self):
    self.seed_success_log()
    outside = self.root.parent / "outside"
    outside.mkdir()
    self.log.rename(outside / self.log.name)
    self.log.parent.rmdir()
    try:
      self.log.parent.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
      self.skipTest("directory symlink unavailable: " + str(error))
    with self.assertRaisesRegex(TerminalTagError, "validation path"):
      self.issue_tag("PASS", push=False)
    self.assertEqual(self.git("tag", "--list"), "")

  def test_symlinked_canonical_log_file_is_rejected(self):
    self.seed_success_log()
    other = self.log.with_name("replacement.jsonl")
    self.log.rename(other)
    try:
      self.log.symlink_to(other)
    except (OSError, NotImplementedError) as error:
      self.skipTest("file symlink unavailable: " + str(error))
    with self.assertRaisesRegex(TerminalTagError, "validation path"):
      self.issue_tag("PASS", push=False)
    self.assertEqual(self.git("tag", "--list"), "")

  def test_traversal_back_into_validation_directory_is_rejected(self):
    self.seed_success_log()
    traversal = self.log.parent / ".." / "validation" / self.log.name
    with self.assertRaisesRegex(TerminalTagError, "validation path"):
      self.issue_tag("PASS", canonical_log=traversal, push=False)
    self.assertEqual(self.git("tag", "--list"), "")

  def test_wrong_subdirectory_with_matching_log_is_rejected(self):
    self.seed_success_log()
    nested = self.log.parent / "other" / self.log.name
    nested.parent.mkdir()
    nested.write_bytes(self.log.read_bytes())
    with self.assertRaisesRegex(TerminalTagError, "validation path"):
      self.issue_tag("PASS", canonical_log=nested, push=False)
    self.assertEqual(self.git("tag", "--list"), "")

  def test_windows_validation_junction_is_rejected_without_is_junction(self):
    if sys.platform != "win32":
      self.skipTest("Windows directory junction test")
    self.seed_success_log()
    outside = self.root.parent / "outside-junction"
    outside.mkdir()
    self.log.rename(outside / self.log.name)
    self.log.parent.rmdir()
    result = subprocess.run(
      ["cmd", "/c", "mklink", "/J", str(self.log.parent), str(outside)],
      capture_output=True, text=True, check=False,
    )
    if result.returncode:
      self.skipTest("Windows junction unavailable: " + result.stderr)
    # Simulate Python 3.10/3.11, before Path.is_junction existed.
    with patch.object(Path, "is_junction", lambda self: False, create=True):
      with self.assertRaisesRegex(TerminalTagError, "validation path"):
        self.issue_tag("PASS", push=False)
    self.assertEqual(self.git("tag", "--list"), "")
  def test_hardlinked_foreign_path_cannot_certify_log(self):
    self.seed_success_log()
    foreign = self.root.parent / self.log.name
    os.link(self.log, foreign)
    with self.assertRaisesRegex(TerminalTagError, "validation path"):
      self.issue_tag("PASS", canonical_log=foreign, push=False)

  def test_swapped_repository_alias_cannot_certify_original_log(self):
    self.seed_success_log()
    alias = self.root.parent / "swapped-root"
    foreign = self.root.parent / "foreign"
    foreign.mkdir()
    alias.symlink_to(self.root, target_is_directory=True)
    alias.unlink()
    alias.symlink_to(foreign, target_is_directory=True)
    with self.assertRaisesRegex(TerminalTagError, "validation path"):
      terminal_tag.verify_phase_evidence(
        alias, self.log, stage="regression", version=VERSION,
        candidate=self.candidate, outcome="PASS")
    alias.unlink()
    alias.symlink_to(self.root, target_is_directory=True)
    validated = terminal_tag._canonical_evidence_log
    def switched(root, supplied):
      expected = validated(root, supplied)
      alias.unlink()
      alias.symlink_to(foreign, target_is_directory=True)
      return expected
    with patch.object(terminal_tag, "_canonical_evidence_log", side_effect=switched):
      with self.assertRaisesRegex(TerminalTagError, "validation path"):
        terminal_tag.verify_phase_evidence(
          alias, self.log, stage="regression", version=VERSION,
          candidate=self.candidate, outcome="PASS")

if __name__ == "__main__":
  unittest.main()
