"""Independent read-only GitHub policy evidence classification for issue 627."""

import unittest


CASES = (
  "direct-push", "force-push", "delete-main", "stale-base",
  "unauthorized-actor", "required-checks", "protected-tags",
)


def classify(response, rule, actor, proof):
  """Certify only provider-observed rejection tied to a matching policy."""
  if not isinstance(response, dict) or response.get("status") != 200:
    return "INCOMPLETE"
  if not isinstance(rule, dict) or rule.get("enabled") is not True:
    return "INCOMPLETE"
  if not isinstance(actor, str) or not actor:
    return "INCOMPLETE"
  if not isinstance(proof, dict) or proof.get("actor") != actor:
    return "INCOMPLETE"
  if proof.get("rule_id") != rule.get("id"):
    return "INCOMPLETE"
  if proof.get("candidate_sha") is None:
    return "INCOMPLETE"
  if (proof.get("rejected") is True\n      and proof.get("provider_status") in (403, 422)\n      and proof.get("provider_reason") == "repository_rule_violation"):
    return "ENFORCED"
  if (proof.get("rejected") is False\n      and proof.get("provider_status") in (200, 201, 204)\n      and proof.get("mutation_verified") is True):
    return "NOT_ENFORCED"
  return "INCOMPLETE"


class ProviderProtectionContractTests(unittest.TestCase):
  def test_seven_independent_acceptance_cases_are_defined(self):
    self.assertEqual(len(CASES), 7)
    self.assertEqual(len(set(CASES)), len(CASES))

  def test_readable_ruleset_alone_does_not_certify_enforcement(self):
    for case in CASES:
      with self.subTest(case=case):
        self.assertEqual(classify({"status": 200}, {"id": 7, "enabled": True},
                                  "untrusted", {}), "INCOMPLETE")

  def test_read_errors_are_incomplete_not_absence(self):
    for status in (0, 401, 403, 404, 429, 500):
      with self.subTest(status=status):
        self.assertEqual(classify({"status": status},
                                  {"id": 7, "enabled": True}, "a", {}),
                         "INCOMPLETE")

  def test_missing_or_disabled_policy_cannot_certify(self):
    proof = {"actor": "a", "rule_id": 7, "candidate_sha": "abc",
             "rejected": True, "provider_status": 403,\n             "provider_reason": "repository_rule_violation"}
    for policy in ({}, {"id": 7, "enabled": False}, None):
      with self.subTest(policy=policy):
        self.assertEqual(classify({"status": 200}, policy, "a", proof),
                         "INCOMPLETE")

  def test_provenance_mismatch_cannot_certify(self):
    rule = {"id": 7, "enabled": True}
    base = {"actor": "a", "rule_id": 7, "candidate_sha": "abc",
            "rejected": True, "provider_status": 403,\n             "provider_reason": "repository_rule_violation"}
    for change in ({"actor": "other"}, {"rule_id": 8},
                   {"candidate_sha": None}, {"provider_status": 500}):
      with self.subTest(change=change):
        self.assertEqual(classify({"status": 200}, rule, "a",
                                  {**base, **change}), "INCOMPLETE")

  def test_positive_provider_rejection_requires_exact_identity(self):
    proof = {"actor": "a", "rule_id": 7, "candidate_sha": "abc",
             "rejected": True, "provider_status": 403,\n             "provider_reason": "repository_rule_violation"}
    self.assertEqual(classify({"status": 200},
                              {"id": 7, "enabled": True}, "a", proof),
                     "ENFORCED")

  def test_generic_permission_403_is_not_protection_evidence(self):\n    proof = {"actor": "a", "rule_id": 7, "candidate_sha": "abc",\n             "rejected": True, "provider_status": 403}\n    self.assertEqual(classify({"status": 200},\n                              {"id": 7, "enabled": True}, "a", proof),\n                     "INCOMPLETE")\n\n  def test_verified_allowed_mutation_is_not_enforced(self):
    proof = {"actor": "a", "rule_id": 7, "candidate_sha": "abc",
             "rejected": False, "provider_status": 201,\n             "mutation_verified": True}
    self.assertEqual(classify({"status": 200},
                              {"id": 7, "enabled": True}, "a", proof),
                     "NOT_ENFORCED")


if __name__ == "__main__":
  unittest.main()
