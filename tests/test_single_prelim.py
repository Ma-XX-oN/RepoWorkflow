"""Operator contract tests for deferred validation and PRELIM generations."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from repo_workflow.done_planner import GateObservation, plan_done
from repo_workflow.prelim_queue import (
  PrelimQueueError, ReadyPrelim, classify_prelims,
)
from tests.test_done_planner import snapshot
from repo_workflow.git import git
from repo_workflow.source_tip import source_tip
from repo_workflow.testing_identity import testing_issue


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
