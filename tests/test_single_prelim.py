"""Operator contract tests for deferred validation and PRELIM generations."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from subprocess import CompletedProcess
from types import SimpleNamespace

from repo_workflow.done_planner import GateObservation, plan_done
from repo_workflow.prelim_queue import (
  PrelimQueueError, ReadyPrelim, classify_prelims,
)
from tests.test_done_planner import snapshot
from repo_workflow.git import git
from repo_workflow.source_tip import source_tip
from repo_workflow.testing_identity import testing_issue
from repo_workflow.prelim_submission import (
  SubmissionError, decode_submission, publish_submission, submission_message, submission_ref,
)
from repo_workflow.integration_host_v2 import IntegrationHost, IntegrationHostError
from adapters.repo_host_github_prelim_submission import read_submission


class SubmissionTests(unittest.TestCase):
  """Submission may defer tests without granting merge authority."""

  def test_missing_tests_and_authorization_allow_submission_not_merge(self):
    """A server request can fill missing tests under later merge authority."""
    plan = plan_done(snapshot(validation=(), authorization=None))
    self.assertTrue(plan.submission_allowed)
    self.assertFalse(plan.allowed)
    self.assertIn("integration-exact-current-PASS", plan.missing_gates)

  def test_current_failure_blocks_submission(self):
    """Current-source FAIL must not be hidden by deferring another stage."""
    facts = snapshot()
    failure = replace(facts.validation[0], status="FAIL")
    self.assertFalse(plan_done(replace(facts, validation=(failure,))).submission_allowed)

  def test_historical_failure_does_not_block_new_source(self):
    """Failures on older material remain historical observations."""
    old = GateObservation("regression", "d" * 40, "b" * 40,
                          "FAIL", True, "provider:old-failure")
    self.assertTrue(plan_done(snapshot(validation=(old,))).submission_allowed)

  def test_stale_parent_requests_reconstruction_not_merge(self):
    """Stale latest submissions remain processable but cannot land as-is."""
    plan = plan_done(snapshot(current_parent_sha="e" * 40))
    self.assertTrue(plan.submission_allowed)
    self.assertFalse(plan.allowed)
    self.assertEqual(plan.disposition, "STALE_BASE")

  def test_invalid_parent_and_incomplete_dependencies_block(self):
    """Deferring tests must not bypass unrelated workflow prerequisites."""
    for facts in (snapshot(parent_branch=None), snapshot(dependencies_complete=False)):
      with self.subTest(facts=facts):
        self.assertFalse(plan_done(facts).submission_allowed)


class PrelimGenerationTests(unittest.TestCase):
  """Latest submission identity is independent of its eventual test result."""

  def prelim(self, number, issue="109"):
    """Construct a qualified immutable submission identity."""
    guid = f"00000000-0000-0000-0000-{number:012d}"
    return ReadyPrelim(f"refs/heads/PRELIM-issue-{issue}/main-{guid}",
                       f"{number:040x}", "issue-" + issue, "main", guid)

  def test_three_categories_and_no_status_based_fallback(self):
    """Only the newest generation can be current, even when it later fails."""
    first, second, latest = (self.prelim(n) for n in (1, 2, 3))
    bases = {first.ref: "a" * 40, second.ref: "b" * 40, latest.ref: "c" * 40}
    predecessors = {first.ref: None, second.ref: first.ref, latest.ref: second.ref}
    positions = classify_prelims((first, second, latest), current_parent_sha="c" * 40,
                                bases=bases, predecessors=predecessors)
    self.assertEqual([item.position for item in positions],
                     ["superseded", "superseded", "current"])
    stale = classify_prelims((first, second, latest), current_parent_sha="d" * 40,
                            bases=bases, predecessors=predecessors)
    self.assertEqual([item.position for item in stale],
                     ["superseded", "superseded", "stale"])

  def test_separate_issues_have_independent_latest_submissions(self):
    """Different issues sharing one parent are not generations of one issue."""
    items = (self.prelim(1), self.prelim(2, "110"))
    result = classify_prelims(items, current_parent_sha="a" * 40,
                             bases={p.ref: "a" * 40 for p in items},
                             predecessors={p.ref: None for p in items})
    self.assertEqual([p.position for p in result], ["current", "current"])

  def test_ambiguous_generations_and_cycles_reject(self):
    """Never infer ordering from names, GUIDs or inventory enumeration."""
    a, b = self.prelim(1), self.prelim(2)
    for prior in ({a.ref: None, b.ref: None}, {a.ref: b.ref, b.ref: a.ref}):
      with self.subTest(prior=prior), self.assertRaises(PrelimQueueError):
        classify_prelims((a, b), current_parent_sha="a" * 40,
                         bases={a.ref: "a" * 40, b.ref: "a" * 40}, predecessors=prior)

  def test_foreign_predecessor_rejects(self):
    """A submission cannot supersede another issue's work."""
    a, b = self.prelim(1), self.prelim(2, "110")
    with self.assertRaises(PrelimQueueError):
      classify_prelims((a, b), current_parent_sha="a" * 40,
                       bases={a.ref: "a" * 40, b.ref: "a" * 40},
                       predecessors={a.ref: None, b.ref: a.ref})


class SourceTipTests(unittest.TestCase):
  """Actual Git history distinguishes source from append-only reports."""

  def setUp(self):
    """Create an isolated repository containing material source."""
    directory = tempfile.TemporaryDirectory()
    self.addCleanup(directory.cleanup)
    self.root = Path(directory.name)
    git(self.root, "init", "-b", "issue-109-test")
    git(self.root, "config", "user.name", "Test")
    git(self.root, "config", "user.email", "test@example.invalid")
    (self.root / "source.txt").write_text("source\n", encoding="utf-8")
    self.original = self.commit()
    self.log = self.root / ".repoworkflow/validation/testResults-109.jsonl"
    self.log.parent.mkdir(parents=True)

  def commit(self):
    """Commit the fixture and return its exact SHA."""
    git(self.root, "add", ".")
    git(self.root, "commit", "-m", "fixture")
    return git(self.root, "rev-parse", "HEAD").stdout.strip()

  def report(self, candidate):
    """Append a structurally valid report without asserting authenticity."""
    with self.log.open("a", encoding="utf-8") as handle:
      handle.write(json.dumps({"testSHA": candidate, "kind": "regression",
                               "runner": "fixture", "result": "succeeded"}) + "\n")
    return self.commit()

  def test_reports_and_resumes_keep_material_source(self):
    """Report commits may name the original source or an earlier report."""
    first = self.report(self.original)
    self.report(first)
    self.assertEqual(source_tip(self.root), self.original)

  def test_mixed_commit_is_source_even_with_report_subject(self):
    """A changed source file prevents report-only peeling."""
    (self.root / "source.txt").write_text("corrected\n", encoding="utf-8")
    changed = self.report(self.original)
    self.assertEqual(source_tip(self.root), changed)

  def test_rewritten_and_foreign_reports_are_material(self):
    """Neither rewriting history nor reporting another source hides a change."""
    self.report(self.original)
    self.log.write_text('{"result":"succeeded"}\n', encoding="utf-8")
    rewritten = self.commit()
    self.assertEqual(source_tip(self.root), rewritten)
    foreign = self.report("a" * 40)
    self.assertEqual(source_tip(self.root), foreign)

  def test_duplicate_fields_cannot_hide_source_change(self):
    """Malformed evidence is material, even if a permissive parser accepts it."""
    self.log.write_text('{"testSHA":"' + self.original + '","kind":"regression",'
                        '"runner":"fixture","result":"failed","result":"succeeded"}\n',
                        encoding="utf-8")
    malformed = self.commit()
    self.assertEqual(source_tip(self.root), malformed)

  def test_prelim_and_arbitrary_branch_resolve_testing_issue(self):
    """Testing ownership survives changing the branch used for execution."""
    self.assertEqual(testing_issue(self.root, branch="PRELIM-issue-109/main-example"), 109)
    self.git_version = self.root / ".ci/engine-version"
    self.git_version.parent.mkdir()
    self.git_version.write_text("1.2.3-issue.109.0.1\n", encoding="utf-8")
    git(self.root, "checkout", "-b", "platform-testing")
    self.assertEqual(testing_issue(self.root), 109)


class SubmissionPublicationTests(unittest.TestCase):
  """Exercise actual atomic Git publication, preserving uncertain local receipts."""

  commit = SourceTipTests.commit

  def setUp(self):
    """Build a source, its parent and an isolated bare provider."""
    SourceTipTests.setUp(self)
    provider = tempfile.TemporaryDirectory()
    self.addCleanup(provider.cleanup)
    self.remote = Path(provider.name)
    git(self.remote, "init", "--bare")
    git(self.root, "remote", "add", "origin", str(self.remote))
    (self.root / "source.txt").write_text("completed source\n", encoding="utf-8")
    self.candidate = self.commit()
    self.guid = "44444444-4444-4444-8444-444444444444"
    self.ref = f"refs/heads/PRELIM-issue-109/main-{self.guid}"
    self.record = {"repository":"Org/Repo", "guid":self.guid, "prelim_ref":self.ref,
                   "source_sha":self.candidate, "candidate_sha":self.candidate,
                   "parent_sha":self.original, "predecessor_ref":None,
                   "inputs_sha256":"f"*64, "release":"patch"}

  def test_publication_and_unchanged_resume_keep_both_objects(self):
    """Publication creates PRELIM and provenance; retry moves neither ref."""
    ready = publish_submission(self.root, self.record, remote="origin")
    self.assertEqual(ready.sha, self.candidate)
    receipt = git(self.remote, "rev-parse", submission_ref(self.guid)).stdout.strip()
    publish_submission(self.root, self.record, remote="origin")
    self.assertEqual(git(self.remote, "rev-parse", submission_ref(self.guid)).stdout.strip(), receipt)
    self.assertEqual(git(self.remote, "rev-parse", self.ref).stdout.strip(), self.candidate)
    self.assertEqual(git(self.root, "rev-parse", "HEAD").stdout.strip(), self.candidate)

  def test_rejected_publication_retains_original_receipt_for_retry(self):
    """A failed transport cannot claim submission, and retry reuses its receipt."""
    real_git = git
    def reject(root, *args, **kwargs):
      if args[0] == "push":
        return CompletedProcess(args, 1, "", "rejected")
      return real_git(root, *args, **kwargs)
    with patch("repo_workflow.prelim_submission.git", side_effect=reject):
      with self.assertRaisesRegex(SubmissionError, "UNKNOWN"):
        publish_submission(self.root, self.record, remote="origin")
    receipt = git(self.root, "rev-parse", submission_ref(self.guid)).stdout.strip()
    self.assertEqual(git(self.remote, "show-ref", check=False).stdout, "")
    publish_submission(self.root, self.record, remote="origin")
    self.assertEqual(git(self.remote, "rev-parse", submission_ref(self.guid)).stdout.strip(), receipt)

  def test_false_parent_and_changed_receipt_reject_without_moving_refs(self):
    """Metadata cannot rewrite ancestry or the identity of a published generation."""
    bad = {**self.record, "parent_sha":"a"*40}
    with self.assertRaises(SubmissionError):
      publish_submission(self.root, bad, remote="origin")
    publish_submission(self.root, self.record, remote="origin")
    with self.assertRaises(SubmissionError):
      publish_submission(self.root, {**self.record, "release":"minor"}, remote="origin")
    self.assertEqual(git(self.remote, "rev-parse", self.ref).stdout.strip(), self.candidate)

  def test_canonical_receipt_rejects_duplicate_fields_and_result_claims(self):
    """Submission metadata has no test-result or merge-authorization field."""
    message = submission_message(self.record)
    self.assertEqual(decode_submission(message, repository="Org/Repo", guid=self.guid), self.record)
    for invalid in (message[:-1] + ',"release":"minor"}',
                    submission_message({**self.record, "outcome":"PASS"})):
      with self.assertRaises(SubmissionError):
        decode_submission(invalid, repository="Org/Repo", guid=self.guid)


class SubmissionProviderTests(unittest.TestCase):
  """Provider fixtures check receipt scope without asserting live certification."""

  def setUp(self):
    """Supply independently pinned provider object and ancestry responses."""
    self.guid = "44444444-4444-4444-8444-444444444444"
    self.record = {"repository":"Org/Repo", "guid":self.guid,
                   "prelim_ref":f"refs/heads/PRELIM-issue-109/main-{self.guid}",
                   "source_sha":"a"*40, "candidate_sha":"b"*40,
                   "parent_sha":"c"*40, "predecessor_ref":None,
                   "inputs_sha256":"f"*64, "release":"patch"}
    self.response = {"ref":submission_ref(self.guid),
                     "object":{"type":"commit","sha":"d"*40}}
    self.receipt = {"sha":"d"*40, "message":submission_message(self.record),
                    "parents":[{"sha":"b"*40}], "tree":{"sha":"e"*40}}
    self.routes = {"git/ref/"+submission_ref(self.guid).removeprefix("refs/"):self.response,
                   "git/commits/"+"d"*40:self.receipt,
                   "git/commits/"+"b"*40:{"sha":"b"*40,"tree":{"sha":"e"*40}},
                   "compare/"+"c"*40+"..."+"b"*40:{"merge_base_commit":{"sha":"c"*40}}}
    self.backend = SimpleNamespace(repository="Org/Repo", get=self.routes.__getitem__)

  def test_provider_record_binds_candidate_tree_and_parent(self):
    """Receipt provenance is checked against physical provider objects."""
    self.assertEqual(read_submission(self.backend, self.guid), self.record)
    self.receipt["tree"]["sha"] = "f"*40
    with self.assertRaisesRegex(SubmissionError, "inputs"):
      read_submission(self.backend, self.guid)

  def test_false_historical_parent_and_foreign_repository_reject(self):
    """Reported roots and namespaces cannot substitute for provider ancestry."""
    route = "compare/"+"c"*40+"..."+"b"*40
    self.routes[route] = {"merge_base_commit":{"sha":"a"*40}}
    with self.assertRaisesRegex(SubmissionError, "ancestry"):
      read_submission(self.backend, self.guid)
    self.backend.repository = "Other/Repo"
    with self.assertRaises(SubmissionError):
      read_submission(self.backend, self.guid)

  def test_host_read_is_scoped_and_cannot_claim_mutation(self):
    """The v2 transport enforces repository and read-only result identity."""
    status, record = "unchanged", self.record
    def transport(request):
      return {**{key:request[key] for key in
                 ("schema_version","repository","operation","request_id")},
              "status":status, "result":{"guid":self.guid,"record":record}}
    host = IntegrationHost("Org/Repo", transport)
    self.assertEqual(host.request("submission.read", "read-1", {"guid":self.guid})["record"], record)
    status = "applied"
    with self.assertRaises(IntegrationHostError):
      host.request("submission.read", "read-2", {"guid":self.guid})
    status, record = "unchanged", {**self.record,"repository":"Other/Repo"}
    with self.assertRaises(IntegrationHostError):
      host.request("submission.read", "read-3", {"guid":self.guid})
