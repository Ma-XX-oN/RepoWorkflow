"""Black-box specification coverage for issue #95."""

import unittest

from repo_workflow.validation_coverage import Coverage, Evidence, Requirement, evaluate


A = "a" * 64
B = "b" * 64


def req(unit="A", fingerprint=A, mode="automated"):
  return Requirement(unit, fingerprint, mode)


def ev(unit="A", fingerprint=A, verdict="PASS",
       mode="automated", provenance="immutable-run/1"):
  return Evidence(unit, fingerprint, verdict, mode, provenance)


class CoverageAcceptance(unittest.TestCase):
  def test_empty_gate_vacuously_complete(self):
    self.assertEqual(evaluate([], []), Coverage(()))
    self.assertTrue(evaluate([], []).complete)

  def test_absent_result_is_missing(self):
    result = evaluate([req()], [])
    self.assertEqual(result.status("A"), "missing")
    self.assertFalse(result.complete)

  def test_matching_pass_satisfies(self):
    self.assertTrue(evaluate([req()], [ev()]).complete)

  def test_changed_fingerprint_stales_previous_pass(self):
    self.assertEqual(evaluate([req(fingerprint=B)], [ev()]).status("A"), "stale")

  def test_failed_or_incomplete_current_result_is_missing(self):
    for verdict in ("FAIL", "INCOMPLETE"):
      with self.subTest(verdict=verdict):
        self.assertEqual(evaluate([req()], [ev(verdict=verdict)]).status("A"), "missing")

  def test_matching_pending_remains_pending(self):
    self.assertEqual(evaluate([req()], [ev(verdict="PENDING")]).status("A"), "pending")

  def test_current_pass_takes_precedence_over_pending_or_fail(self):
    results = [ev(verdict="FAIL"), ev(verdict="PENDING"), ev()]
    self.assertTrue(evaluate([req()], results).complete)

  def test_broader_run_satisfies_narrower_required_set(self):
    broad = [ev("A"), ev("B")]
    self.assertTrue(evaluate([req("A")], broad).complete)

  def test_independent_subset_runs_collectively_satisfy_full_set(self):
    obligations = [req("A"), req("B"), req("C")]
    results = [ev("A", provenance="fast/1"),
               ev("B", provenance="fast/1"),
               ev("C", provenance="group/2")]
    self.assertTrue(evaluate(obligations, results).complete)

  def test_fast_label_never_grants_unexecuted_coverage(self):
    obligations = [req("A"), req("B"), req("C")]
    result = evaluate(obligations, [ev("A", provenance="fast/1")])
    self.assertEqual(result.statuses, (
      ("A", "satisfied"), ("B", "missing"), ("C", "missing")
    ))

  def test_mit_never_uses_automated_pass(self):
    manual = req("MIT", mode="manual")
    result = evaluate([manual], [ev("MIT", mode="automated")])
    self.assertEqual(result.status("MIT"), "stale")
    self.assertFalse(result.complete)

  def test_manual_pass_satisfies_only_manual_requirement(self):
    self.assertTrue(evaluate([req("MIT", mode="manual")],
                             [ev("MIT", mode="manual")]).complete)

  def test_changed_input_invalidates_only_affected_unit(self):
    obligations = [req("A", fingerprint=B), req("B")]
    result = evaluate(obligations, [ev("A"), ev("B")])
    self.assertEqual(result.statuses, (("A", "stale"), ("B", "satisfied")))

  def test_provider_agnostic_and_order_independent(self):
    obligations = [req("A"), req("B")]
    local = ev("A", provenance="local/1")
    hosted = ev("B", provenance="hosted/2")
    a = evaluate(obligations, [local, hosted])
    b = evaluate(list(reversed(obligations)), [hosted, local])
    self.assertEqual(a, b)

  def test_duplicate_requirement_fails_closed(self):
    with self.assertRaises(ValueError):
      evaluate([req(), req()], [])

  def test_invalid_evidence_and_requirement_fails_closed(self):
    for invalid in ([object()], [None]):
      with self.assertRaises(ValueError):
        evaluate([req()], invalid)
      with self.assertRaises(ValueError):
        evaluate(invalid, [])

  def test_invalid_fingerprint_and_verdict_fail_closed(self):
    with self.assertRaises(ValueError):
      req(fingerprint="not-sha")
    with self.assertRaises(ValueError):
      ev(verdict="SUCCESS")


if __name__ == "__main__":
  unittest.main()
