"""Black-box validation of provider-backed candidate/base facts (#104)."""
import unittest
from dataclasses import replace
from repo_workflow.candidate_eligibility import Facts, decide
from repo_workflow.github_host_facts import (
  HostFactsError, read_host_facts, decide_with_github_host,
)

CANDIDATE = "a" * 40
BASE = "b" * 40


def provider(head=CANDIDATE, base=BASE, status="ahead"):
  def fetch(path):
    if path == "/branches/feature%2Fwork":
      return {"commit": {"sha": head}}
    if path == "/branches/main":
      return {"commit": {"sha": base}}
    if path == "/compare/" + base + "..." + CANDIDATE:
      return {"status": status, "base_commit": {"sha": base}}
    raise AssertionError("unexpected provider lookup: " + path)
  return fetch


def observe(fetch):
  return read_host_facts(
    "owner/repo", "feature/work", "main", CANDIDATE,
    "test-token", fetch=fetch,
  )


class HostFactsTests(unittest.TestCase):
  def test_live_provider_facts_change_candidate_verdict(self):
    original = Facts(
      CANDIDATE, CANDIDATE, CANDIDATE, BASE, BASE,
      True, True, True, True, True, True, True, True,
    )
    cases = (
      (CANDIDATE, BASE, "ahead", None),
      ("c" * 40, BASE, "ahead", "head-changed"),
      (CANDIDATE, "d" * 40, "ahead", "stale-base"),
      (CANDIDATE, BASE, "behind", "missing-base_is_ancestor"),
      (CANDIDATE, BASE, "diverged", "missing-base_is_ancestor"),
    )
    for head, base, status, reason in cases:
      with self.subTest(head=head, base=base, status=status):
        host = observe(provider(head, base, status))
        facts = replace(
          original, head=host.head, current_base=host.current_base,
          candidate_exists=host.candidate_exists,
          base_is_ancestor=host.base_is_ancestor,
        )
        ok, reasons = decide(facts)
        self.assertEqual(ok, reason is None)
        if reason is not None:
          self.assertIn(reason, reasons)


  def test_binding_overrides_forged_host_flags_and_fails_closed(self):
    forged = Facts(
      CANDIDATE, CANDIDATE, "c" * 40, BASE, "d" * 40,
      True, True, True, True, True, True, True, True,
    )
    args = ("owner/repo", "feature/work", "main", "test-token")
    self.assertEqual(decide_with_github_host(
      forged, *args, fetch=provider(),
    ), (True, ()))
    self.assertEqual(decide_with_github_host(
      forged, *args, fetch=provider(head="c" * 40),
    ), (False, ("head-changed",)))
    self.assertEqual(decide_with_github_host(
      forged, *args, fetch=lambda _: None,
    ), (False, ("host-facts-unavailable",)))
    self.assertEqual(decide_with_github_host(
      None, *args, fetch=provider(),
    ), (False, ("invalid-facts",)))

  def test_malformed_and_unavailable_provider_data_refused(self):
    with self.assertRaises(HostFactsError):
      observe(lambda _: None)
    with self.assertRaises(HostFactsError):
      observe(lambda _: (_ for _ in ()).throw(OSError("offline")))
    for invalid in (
      {"status": "unknown", "base_commit": {"sha": BASE}},
      {"status": "ahead", "base_commit": {"sha": "f" * 40}},
    ):
      with self.subTest(invalid=invalid):
        def fetch(path):
          if path.startswith("/compare/"):
            return invalid
          return provider()(path)
        with self.assertRaises(HostFactsError):
          observe(fetch)

  def test_invalid_identifiers_never_reach_provider(self):
    for repo, source, candidate, token in (
      ("../other", "feature/work", CANDIDATE, "token"),
      ("owner/repo", "../escape", CANDIDATE, "token"),
      ("owner/repo", "feature//work", CANDIDATE, "token"),
      ("owner/repo", "feature/work", "bad", "token"),
      ("owner/repo", "feature/work", CANDIDATE, ""),
    ):
      with self.subTest(repo=repo, source=source):
        with self.assertRaises(HostFactsError):
          read_host_facts(
            repo, source, "main", candidate, token,
            fetch=lambda _: self.fail("untrusted input reached provider"),
          )


if __name__ == "__main__":
  unittest.main()
