from __future__ import annotations

import json
from pathlib import Path
import unittest

from repo_workflow.public_commands import COMMANDS


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "FIRST_USE_WORKFLOWS.json"
AUDIT = ROOT / "FIRST_USE_WORKFLOW_AUDIT.md"


def executable_static_paths(
  node: dict,
  prefix: tuple[str, ...] = (),
) -> set[tuple[str, ...]]:
  result: set[tuple[str, ...]] = set()
  if prefix and (
    "" in node
    or "_values" in node
    or "_variadic" in node
  ):
    result.add(prefix)

  for token, entry in node.items():
    if not token or token.startswith("_"):
      continue
    current = (*prefix, token)
    if isinstance(entry, str):
      result.add(current)
    else:
      result.update(executable_static_paths(entry, current))
  return result


def verification_target_exists(target: str) -> bool:
  if "::" not in target:
    return False
  path_text, symbol = target.split("::", 1)
  path = ROOT / path_text
  if not path.is_file():
    return False
  if symbol == "FILE_LEVEL_COVERAGE":
    return False
  method = symbol.rsplit(".", 1)[-1]
  return f"def {method}(" in path.read_text(encoding="utf-8")


class FirstUseWorkflowRegistryTests(unittest.TestCase):
  def registry(self) -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))

  def test_every_executable_public_command_path_has_first_use_owner(self):
    value = self.registry()
    mappings = {
      tuple(prefix.split()): scenario
      for prefix, scenario in value["public_prefixes"].items()
    }
    exemptions = {
      tuple(prefix.split()): reason
      for prefix, reason in value["exempt_prefixes"].items()
    }
    scenarios = {item["id"] for item in value["scenarios"]}

    missing: list[str] = []
    unknown_scenarios: list[str] = []
    for path in sorted(executable_static_paths(COMMANDS)):
      matches = [
        (prefix, scenario)
        for prefix, scenario in mappings.items()
        if path[:len(prefix)] == prefix
      ]
      exempt = [
        prefix
        for prefix in exemptions
        if path[:len(prefix)] == prefix
      ]
      if not matches and not exempt:
        missing.append(" ".join(path))
        continue
      if matches:
        _, scenario = max(matches, key=lambda item: len(item[0]))
        if scenario not in scenarios:
          unknown_scenarios.append(
            f"{' '.join(path)} -> {scenario}"
          )

    self.assertEqual(
      missing,
      [],
      "public command paths lack first-use ownership",
    )
    self.assertEqual(
      unknown_scenarios,
      [],
      "public command paths reference unknown first-use scenarios",
    )

  def test_covered_scenarios_name_real_tests_and_gaps_have_issue_owner(self):
    value = self.registry()
    for scenario in value["scenarios"]:
      with self.subTest(scenario=scenario["id"]):
        status = scenario["status"]
        self.assertIn(status, {"covered", "gap", "pending"})
        if status == "covered":
          tests = scenario.get("tests", [])
          self.assertTrue(tests)
          for test in tests:
            self.assertTrue(
              (ROOT / test).is_file(),
              f"{scenario['id']} references missing test {test}",
            )
        else:
          self.assertIsInstance(scenario.get("gap_issue"), int)
          self.assertGreater(scenario["gap_issue"], 0)

  def test_covered_scenarios_trace_each_acceptance_requirement_to_tests(self):
    value = self.registry()
    for scenario in value["scenarios"]:
      acceptance = scenario.get("acceptance", [])
      self.assertTrue(
        acceptance,
        f"{scenario['id']} has no acceptance traceability matrix",
      )
      ids = [item.get("id") for item in acceptance]
      self.assertEqual(
        len(ids),
        len(set(ids)),
        f"{scenario['id']} has duplicate acceptance IDs",
      )
      for item in acceptance:
        with self.subTest(scenario=scenario["id"], acceptance=item.get("id")):
          self.assertIsInstance(item.get("requirement"), str)
          self.assertTrue(item["requirement"].strip())
          verification = item.get("verification")
          deferred = item.get("deferred_issue")
          self.assertNotEqual(
            bool(verification),
            bool(deferred),
            "acceptance item must have exactly one of verification/deferred_issue",
          )
          if scenario["status"] == "covered":
            self.assertTrue(
              verification,
              f"covered scenario {scenario['id']} defers {item['id']}",
            )
          if verification:
            for target in verification:
              self.assertTrue(
                verification_target_exists(target),
                f"missing executable verification target: {target}",
              )
          else:
            self.assertIsInstance(deferred, int)
            self.assertGreater(deferred, 0)

  def test_covered_stateful_scenarios_trace_lifecycle_dimensions(self):
    value = self.registry()
    for scenario in value["scenarios"]:
      if scenario["status"] != "covered" or not scenario.get("stateful"):
        continue
      acceptance_ids = {item["id"] for item in scenario["acceptance"]}
      dimensions = scenario.get("lifecycle_dimensions")
      self.assertIsInstance(
        dimensions,
        dict,
        f"{scenario['id']} lacks lifecycle dimensions",
      )
      self.assertTrue(dimensions, f"{scenario['id']} has empty lifecycle dimensions")
      unknown = set(dimensions.values()) - acceptance_ids
      self.assertEqual(
        unknown,
        set(),
        f"{scenario['id']} lifecycle dimensions reference unknown acceptance IDs",
      )

  def test_covered_provider_scenarios_verify_external_contract_fidelity(self):
    value = self.registry()
    for scenario in value["scenarios"]:
      if scenario["status"] != "covered" or not scenario.get("provider_boundary"):
        continue
      targets = scenario.get("provider_contract_verification", [])
      self.assertTrue(
        targets,
        f"{scenario['id']} lacks provider contract verification",
      )
      for target in targets:
        self.assertTrue(
          verification_target_exists(target),
          f"missing provider contract verifier: {target}",
        )

  def test_audit_row_count_matches_registry_snapshot(self):
    value = self.registry()
    rows = [
      line
      for line in AUDIT.read_text(encoding="utf-8").splitlines()
      if line.startswith("| #")
    ]
    numbers = [
      int(line.split("|", 2)[1].strip().removeprefix("#"))
      for line in rows
    ]
    self.assertEqual(len(numbers), value["audited_issue_count"])
    self.assertEqual(len(numbers), len(set(numbers)))
    self.assertEqual(max(numbers), value["audited_through_issue"])


if __name__ == "__main__":
  unittest.main()
