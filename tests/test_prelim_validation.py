"""Issue #102: immutable PRELIM identity and negative transitions."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from repo_workflow.git import git
from repo_workflow.prelim_attempt import construct_prelim
from repo_workflow.prelim_publication import (
  PrelimPublicationError, restore_identity,
)
from repo_workflow.prelim_validation import (
  HostedObservation, PrelimValidationError, validate_prelim,
)
from repo_workflow.state_store import StateStoreError, durable_store


class PrelimValidationTests(unittest.TestCase):
  def setUp(self):
    # Reuse the independently tested #82 real Git/bare-provider fixture.
    from tests.test_prelim_attempt import PrelimAttemptTests
    PrelimAttemptTests.setUp(self)
    self.candidate = construct_prelim(
      self.root, "7", "refs/heads/issue-7", self.config,
    )
    self.version = "1.2.3-issue.7.0.1"
    self.regression = HostedObservation(
      self.root, "a" * 40, 1001, self.root / "regression.jsonl",
    )
    self.integration = HostedObservation(
      self.root, "b" * 40, 1002, self.root / "integration.jsonl",
    )

  def publish_tags(self):
    version = self.version
    for tag in ("v" + version, "v1.2.3-PRELIM-7.0.1"):
      git(self.root, "tag", "-a", tag, self.candidate.candidate_sha,
          "-m", tag)
      git(self.root, "push", "origin", "refs/tags/" + tag)

  def invoke(self, observations):
    with patch("repo_workflow.prelim_validation._observation",
               side_effect=observations):
      return validate_prelim(
        self.root, self.candidate.attempt, self.config,
        regression=self.regression, integration=self.integration,
      )

  def pass_results(self):
    return [
      {"outcome": "PASS", "version": self.version,
       "tag": "v" + self.version},
      {"outcome": "PASS", "version": self.version,
       "tag": "v1.2.3-PRELIM-7.0.1"},
    ]

  def identity(self):
    return durable_store(self.root).read(
      "prelim/identities/" + self.candidate.attempt
    )

  def test_two_verified_passes_and_provider_tags_accept_immutable_identity(self):
    self.publish_tags()
    first = self.invoke(self.pass_results())
    second = self.invoke(self.pass_results())
    self.assertEqual(first, second)
    self.assertEqual(first.outcome, "PASS")
    self.assertEqual(first.identity_version, self.version)
    self.assertEqual(self.identity()["revision"], 0)
    self.assertEqual(self.identity()["value"]["candidate_sha"],
                     self.candidate.candidate_sha)
    self.assertEqual(git(self.root, "rev-parse", "issue-7").stdout.strip(),
                     self.source)

  def test_missing_published_prelim_tag_fails_closed(self):
    with self.assertRaisesRegex(PrelimValidationError, "tag"):
      self.invoke(self.pass_results())
    with self.assertRaises(StateStoreError):
      self.identity()

  def test_failed_terminal_evidence_audited_but_never_accepted(self):
    checks = self.pass_results()
    checks[1] = {"outcome": "FAIL", "version": self.version,
                 "tag": "v1.2.3-PRELIM-7.0.1-CI-FAIL"}
    result = self.invoke(checks)
    self.assertEqual(result.outcome, "FAIL")
    with self.assertRaises(StateStoreError):
      self.identity()
    self.assertEqual(len(list(
      (self.root / ".repoworkflow/state/prelim/validations" /
       self.candidate.attempt).glob("*.json")
    )), 1)

  def test_incomplete_remains_audited_without_acceptance(self):
    checks = self.pass_results()
    checks[0] = {"outcome": "INCOMPLETE", "version": None, "tag": None}
    self.assertEqual(self.invoke(checks).outcome, "INCOMPLETE")
    with self.assertRaises(StateStoreError):
      self.identity()

  def test_candidate_remote_ref_rewrite_blocks_acceptance(self):
    self.publish_tags()
    git(self.root, "push", "origin", "+refs/heads/main:refs/heads/" +
        self.candidate.branch)
    with self.assertRaisesRegex(PrelimValidationError, "candidate changed"):
      self.invoke(self.pass_results())
    with self.assertRaises(StateStoreError):
      self.identity()

  def test_conflicting_evidence_for_same_invocations_rejected(self):
    self.publish_tags()
    self.invoke(self.pass_results())
    checks = self.pass_results()
    checks[1] = {"outcome": "FAIL", "version": self.version,
                 "tag": "v1.2.3-PRELIM-7.0.1-CI-FAIL"}
    with self.assertRaisesRegex(PrelimValidationError, "immutable"):
      self.invoke(checks)
    self.assertEqual(self.identity()["value"]["outcome"], "PASS")

  def test_different_test_versions_rejected(self):
    checks = self.pass_results()
    checks[1]["version"] = "1.2.3-issue.7.0.2"
    with self.assertRaisesRegex(PrelimValidationError, "different versions"):
      self.invoke(checks)

  def test_provider_identity_is_durable_and_restorable(self):
    self.publish_tags()
    accepted = self.invoke(self.pass_results())
    reference = ("refs/heads/prelim-identity-state/" +
                 self.candidate.attempt)
    advertised = git(self.root, "ls-remote", "origin", reference)
    self.assertEqual(len(advertised.stdout.splitlines()), 1)
    fresh = Path(self.temp.name) / "identity-fresh-clone"
    git(self.root, "clone", "--branch", "main", str(self.remote),
        str(fresh))
    restore_identity(fresh, "origin", self.candidate.attempt)
    found = durable_store(fresh).read(
      "prelim/identities/" + self.candidate.attempt
    )
    self.assertEqual(found, self.identity())
    self.assertEqual(found["value"]["candidate_sha"],
                     accepted.candidate_sha)

  def test_provider_identity_rewrite_is_rejected(self):
    self.publish_tags()
    self.invoke(self.pass_results())
    reference = ("refs/heads/prelim-identity-state/" +
                 self.candidate.attempt)
    git(self.root, "push", "origin", "+refs/heads/main:" + reference)
    with self.assertRaises(PrelimPublicationError):
      restore_identity(self.root, "origin", self.candidate.attempt)
    with self.assertRaises(PrelimPublicationError):
      self.invoke(self.pass_results())

  def test_no_production_stable_tag_created(self):
    self.publish_tags()
    self.invoke(self.pass_results())
    tags = git(self.root, "ls-remote", "--tags", "origin").stdout
    self.assertNotIn("refs/tags/v1.2.4", tags)
    self.assertNotIn("refs/tags/v1.2.3", tags)

  def test_rejects_unready_attempt(self):
    record = durable_store(self.root).read(
      "prelim/attempts/" + self.candidate.attempt
    )
    value = dict(record["value"])
    value["state"] = "versioned"
    value["candidate_sha"] = None
    durable_store(self.root).replace(
      record["key"], record["revision"], value, self.writer,
    )
    with self.assertRaisesRegex(PrelimValidationError, "not ready"):
      self.invoke(self.pass_results())


if __name__ == "__main__":
  unittest.main()
