"""Real Git contract tests for hosted version and retry identity."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.hosted_version_identity import (
  HostedVersionError, resolve_hosted_version, resolve_invocation,
)

VERSION = "0.1.121-issue.570.0.1"


class HostedIdentityTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    self.git("init", "-q", "-b", "issue-570-source")
    self.git("config", "user.name", "Fixture")
    self.git("config", "user.email", "fixture@example.invalid")
    (self.root / "source").write_text("candidate\n")
    self.git("add", "source")
    self.git("commit", "-qm", "candidate")
    self.candidate = self.git("rev-parse", "HEAD")
    self.log = self.root / ".repoworkflow/validation/testResults-570.jsonl"
    self.log.parent.mkdir(parents=True)

  def git(self, *args):
    return subprocess.check_output(
      ["git", "-C", str(self.root), *args], text=True,
    ).strip()

  def invoke(self, stage="regression", sha=None):
    tip = self.git("rev-parse", "HEAD")
    marker = self.root / ".ci/run"
    marker.parent.mkdir(exist_ok=True)
    marker.write_text(("temp" if stage == "temporary" else stage) + "-testing " + (sha or tip) + "\n")
    self.git("add", ".ci/run")
    self.git("commit", "-qm", "request")
    return self.git("rev-parse", "HEAD")

  def evidence(self, **changes):
    record = {
      "testSHA": self.candidate, "kind": "regression",
      "branch": "issue-570-source", "testVersion": VERSION,
      "result": "succeeded", "runner": "hosted",
      "headChangedDuringTest": False, "uncommittedChanges": [],
    }
    record.update(changes)
    with self.log.open("a") as out:
      out.write(json.dumps(record) + "\n")

  def test_nonexistent_and_malformed_invocation_sha(self):
    for candidate in ("not-sha", "A" * 40, "f" * 40):
      with self.subTest(candidate=candidate):
        with self.assertRaises(HostedVersionError):
          resolve_invocation(self.root, candidate)

  def test_non_invocation_source_commit_rejected(self):
    with self.assertRaisesRegex(HostedVersionError, "not a hosted invocation"):
      resolve_invocation(self.root, self.candidate)

  def test_malformed_marker_extra_field_rejected(self):
    parent = self.git("rev-parse", "HEAD")
    path = self.root / ".ci/run"
    path.parent.mkdir(exist_ok=True)
    path.write_text("regression-testing " + parent + " third\n")
    self.git("add", ".ci/run")
    self.git("commit", "-qm", "bad request")
    with self.assertRaisesRegex(HostedVersionError, "invalid two-field"):
      resolve_invocation(self.root, self.git("rev-parse", "HEAD"))

  def test_empty_marker_rejected(self):
    path = self.root / ".ci/run"
    path.parent.mkdir(exist_ok=True)
    path.write_text("")
    self.git("add", ".ci/run")
    self.git("commit", "-qm", "empty request")
    with self.assertRaisesRegex(HostedVersionError, "invalid two-field"):
      resolve_invocation(self.root, self.git("rev-parse", "HEAD"))

  def test_first_request_binds_immediate_parent_and_original_candidate(self):
    sha = self.invoke()
    result = resolve_invocation(self.root, sha)
    self.assertEqual(result["request_parent_sha"], self.candidate)
    self.assertEqual(result["candidate_sha"], self.candidate)
    self.assertEqual(result["retry_depth"], 0)

  def test_two_retries_preserve_first_source_identity(self):
    self.invoke()
    second = self.invoke()
    third = self.invoke()
    result = resolve_invocation(self.root, third)
    self.assertEqual(result["request_parent_sha"], second)
    self.assertEqual(result["candidate_sha"], self.candidate)
    self.assertEqual(result["retry_depth"], 2)

  def test_version_comes_only_from_matching_canonical_evidence(self):
    sha = self.invoke()
    self.assertIsNone(resolve_hosted_version(self.root, sha, self.log)["test_version"])
    self.evidence()
    self.assertEqual(
      resolve_hosted_version(self.root, sha, self.log)["test_version"], VERSION,
    )
    self.assertEqual(
      resolve_hosted_version(self.root, self.invoke(), self.log)["test_version"],
      VERSION,
    )

  def test_engine_self_without_version_does_not_invent_one(self):
    sha = self.invoke()
    self.assertIsNone(resolve_hosted_version(self.root, sha, self.log)["test_version"])

  def test_wrong_candidate_and_phase_do_not_supply_version(self):
    sha = self.invoke()
    self.evidence(testSHA="f" * 40, testVersion="0.1.121-issue.570.0.2")
    self.evidence(kind="integration", testVersion="0.1.121-issue.570.0.3")
    self.assertIsNone(resolve_hosted_version(self.root, sha, self.log)["test_version"])

  def test_conflicting_pass_and_fail_for_same_terminal_version(self):
    sha = self.invoke()
    self.evidence(result="succeeded")
    self.evidence(result="failed")
    with self.assertRaisesRegex(HostedVersionError, "conflicting terminal"):
      resolve_hosted_version(self.root, sha, self.log)

  def test_repeated_identical_terminal_outcome_is_idempotent(self):
    sha = self.invoke()
    self.evidence(result="succeeded")
    self.evidence(result="succeeded")
    self.assertEqual(resolve_hosted_version(self.root, sha, self.log)["test_version"],
                     VERSION)

  def test_conflicting_versions_are_rejected(self):
    sha = self.invoke()
    self.evidence()
    self.evidence(testVersion="0.1.121-issue.570.0.2")
    with self.assertRaisesRegex(HostedVersionError, "conflicting"):
      resolve_hosted_version(self.root, sha, self.log)

  def test_dirty_terminal_evidence_cannot_allocate_version(self):
    sha = self.invoke()
    self.evidence(uncommittedChanges=["source"])
    with self.assertRaisesRegex(HostedVersionError, "dirty"):
      resolve_hosted_version(self.root, sha, self.log)

  def test_moved_head_terminal_evidence_cannot_allocate_version(self):
    sha = self.invoke()
    self.evidence(headChangedDuringTest=True)
    with self.assertRaisesRegex(HostedVersionError, "moved"):
      resolve_hosted_version(self.root, sha, self.log)

  def test_incomplete_only_does_not_allocate_terminal_version(self):
    sha = self.invoke()
    self.evidence(result="incomplete")
    self.assertIsNone(resolve_hosted_version(self.root, sha, self.log)["test_version"])

  def test_incomplete_followed_by_complete_preserves_same_version(self):
    sha = self.invoke()
    self.evidence(result="incomplete")
    self.evidence(result="succeeded")
    self.assertEqual(resolve_hosted_version(self.root, sha, self.log)["test_version"],
                     VERSION)

  def test_incomplete_candidate_does_not_consume_version_for_new_candidate(self):
    sha = self.invoke()
    self.evidence(testSHA="f" * 40, result="incomplete")
    self.evidence(result="succeeded")
    self.assertEqual(resolve_hosted_version(self.root, sha, self.log)["test_version"],
                     VERSION)

  def test_same_version_cannot_claim_two_candidates(self):
    sha = self.invoke()
    self.evidence()
    self.evidence(testSHA="f" * 40)
    with self.assertRaisesRegex(HostedVersionError, "different candidate"):
      resolve_hosted_version(self.root, sha, self.log)

  def test_other_candidate_with_distinct_version_is_ignored(self):
    sha = self.invoke()
    self.evidence()
    self.evidence(testSHA="f" * 40,
                  testVersion="0.1.121-issue.570.0.2")
    self.assertEqual(resolve_hosted_version(self.root, sha, self.log)["test_version"],
                     VERSION)

  def test_same_version_cannot_claim_two_terminal_phases(self):
    sha = self.invoke()
    self.evidence()
    self.evidence(kind="integration")
    with self.assertRaisesRegex(HostedVersionError, "different candidate or phase"):
      resolve_hosted_version(self.root, sha, self.log)

  def test_different_version_other_phase_does_not_conflict(self):
    sha = self.invoke()
    self.evidence()
    self.evidence(kind="integration", testVersion="0.1.121-issue.570.0.2")
    self.assertEqual(resolve_hosted_version(self.root, sha, self.log)["test_version"],
                     VERSION)

  def test_wrong_issue_or_branch_evidence_is_rejected(self):
    sha = self.invoke()
    self.evidence(branch="issue-571-other")
    with self.assertRaisesRegex(HostedVersionError, "another branch"):
      resolve_hosted_version(self.root, sha, self.log)

  def test_version_path_outside_canonical_validation_directory_fails(self):
    sha = self.invoke()
    outside = self.root / "testResults-570.jsonl"
    outside.write_text("{}\n")
    with self.assertRaisesRegex(HostedVersionError, "canonical"):
      resolve_hosted_version(self.root, sha, outside)

  def test_wrong_issue_version_record_rejected(self):
    sha = self.invoke()
    self.evidence(testVersion="0.1.121-issue.571.0.1")
    with self.assertRaisesRegex(HostedVersionError, "issue"):
      resolve_hosted_version(self.root, sha, self.log)

  def test_symlinked_version_log_rejected(self):
    sha = self.invoke()
    outside = self.root / "external.jsonl"
    outside.write_text("{}\n")
    self.log.symlink_to(outside)
    with self.assertRaisesRegex(HostedVersionError, "canonical"):
      resolve_hosted_version(self.root, sha, self.log)

  def test_non_utf8_version_log_fails_closed(self):
    sha = self.invoke()
    self.log.write_bytes(b"\\xff\\xfe")
    with self.assertRaisesRegex(HostedVersionError, "cannot read"):
      resolve_hosted_version(self.root, sha, self.log)

  def test_version_lookup_does_not_publish_tags(self):
    sha = self.invoke()
    self.evidence()
    self.assertEqual(resolve_hosted_version(self.root, sha, self.log)["test_version"],
                     VERSION)
    self.assertEqual(self.git("tag", "--list"), "")

  def test_malformed_json_fails_closed(self):
    sha = self.invoke()
    self.log.write_text("{malformed\n")
    with self.assertRaisesRegex(HostedVersionError, "malformed"):
      resolve_hosted_version(self.root, sha, self.log)

  def test_incorrect_parent_marker_cannot_be_accepted(self):
    sha = self.invoke(sha="a" * 40)
    with self.assertRaisesRegex(HostedVersionError, "immediate parent"):
      resolve_invocation(self.root, sha)

  def test_non_marker_mutation_in_request_fails(self):
    tip = self.git("rev-parse", "HEAD")
    path = self.root / ".ci/run"
    path.parent.mkdir(exist_ok=True)
    path.write_text("regression-testing " + tip + "\n")
    (self.root / "source").write_text("changed\n")
    self.git("add", ".ci/run", "source")
    self.git("commit", "-qm", "invalid multi-path invocation")
    with self.assertRaisesRegex(HostedVersionError, "immediate parent|non-marker"):
      resolve_invocation(self.root, self.git("rev-parse", "HEAD"))

  def test_absent_terminal_version_for_nonterminal_phase(self):
    sha = self.invoke(stage="GREEN")
    self.evidence()
    self.assertIsNone(resolve_hosted_version(self.root, sha, self.log)["test_version"])

  def test_different_hosted_stage_after_request_is_valid(self):
    self.invoke(stage="GREEN")
    sha = self.invoke(stage="regression")
    result = resolve_invocation(self.root, sha)
    self.assertEqual(result["stage"], "regression")
    self.assertEqual(result["candidate_sha"], self.candidate)
    self.assertEqual(result["retry_depth"], 0)
    self.assertEqual(result["stage_transition_count"], 1)

  def test_stage_transition_then_same_stage_retry(self):
    self.invoke(stage="GREEN")
    self.invoke(stage="regression")
    sha = self.invoke(stage="regression")
    result = resolve_invocation(self.root, sha)
    self.assertEqual(result["stage"], "regression")
    self.assertEqual(result["candidate_sha"], self.candidate)
    self.assertEqual(result["retry_depth"], 1)
    self.assertEqual(result["stage_transition_count"], 1)

  def test_inherited_marker_on_head_is_not_new_invocation(self):
    self.invoke()
    (self.root / "source").write_text("next source\n")
    self.git("add", "source")
    self.git("commit", "-qm", "source with unchanged marker")
    with self.assertRaisesRegex(HostedVersionError, "immediate parent|non-marker"):
      resolve_invocation(self.root, self.git("rev-parse", "HEAD"))

  def test_temporary_marker_uses_public_stage_spelling(self):
    sha = self.invoke(stage="temporary")
    self.assertEqual(resolve_invocation(self.root, sha)["stage"], "temporary")

  def test_malformed_version_record_without_result_fails_closed(self):
    sha = self.invoke()
    self.evidence(result=None)
    with self.assertRaisesRegex(HostedVersionError, "valid result"):
      resolve_hosted_version(self.root, sha, self.log)

  def test_non_object_log_entry_rejected(self):
    sha = self.invoke()
    self.log.write_text("[]\n")
    with self.assertRaisesRegex(HostedVersionError, "non-object"):
      resolve_hosted_version(self.root, sha, self.log)

  def test_inherited_marker_on_source_commit_does_not_become_retry(self):
    self.invoke()
    (self.root / "source").write_text("next source\n")
    self.git("add", "source")
    self.git("commit", "-qm", "source advance preserving marker")
    new_candidate = self.git("rev-parse", "HEAD")
    self.invoke()
    sha = self.git("rev-parse", "HEAD")
    result = resolve_invocation(self.root, sha)
    self.assertEqual(result["candidate_sha"], new_candidate)
    self.assertEqual(result["retry_depth"], 0)


if __name__ == "__main__":
  unittest.main()
