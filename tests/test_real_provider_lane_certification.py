from __future__ import annotations

import json
from pathlib import Path
import unittest

from repo_workflow.dependency_migration_certification import (
  require_dependency_migration_certified,
)


ROOT = Path(__file__).resolve().parents[1]
AUDIT = (
  ROOT
  / ".repoworkflow"
  / "audit"
  / "issue-327-real-provider-certification--run-37279057867.json"
)
MANIFEST = (
  ROOT
  / ".repoworkflow"
  / "migrations"
  / "native-dependencies-v1.json"
)
CACHE_ROUTING_AUDIT = (
  ROOT
  / ".repoworkflow"
  / "audit"
  / "issue-346-lane-cache-routing-certification--run-37352056494.json"
)


class RealProviderLaneCertificationTests(unittest.TestCase):
  def audit(self) -> dict:
    return json.loads(AUDIT.read_text(encoding="utf-8"))

  def test_committed_certification_matches_manifest_and_full_provider_readback(self):
    require_dependency_migration_certified(ROOT)

    audit = self.audit()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    issue_count = len(manifest["issues"])

    self.assertEqual(audit["issue"], 327)
    self.assertEqual(
      audit["migration"]["post_apply_counts"],
      {
        "MATCH": issue_count,
        "DESTINATION_EMPTY": 0,
        "CONFLICT": 0,
      },
    )
    self.assertEqual(
      audit["certification"]["provider_counts"],
      {
        "MATCH": issue_count,
        "DESTINATION_EMPTY": 0,
        "CONFLICT": 0,
      },
    )
    self.assertEqual(
      audit["migration"]["provider_readback_sha256"],
      "7312c52a9d695f1a10468dc3dfd12fd887424acce65962f0d782a5b2e4c0a5d0",
    )

  def test_real_provider_cache_and_routing_certification(self):
    audit = json.loads(CACHE_ROUTING_AUDIT.read_text(encoding="utf-8"))

    self.assertEqual(audit["issue"], 346)
    self.assertEqual(audit["workflow_run_id"], 37352056494)
    self.assertEqual(audit["first_select"]["roots"], ["218"])
    self.assertIn("145", audit["first_select"]["closure"])
    self.assertIn("216", audit["first_select"]["closure"])

    self.assertEqual(audit["local_inspection"]["provider_requests"], 0)
    self.assertTrue(audit["local_inspection"]["invalid_token_local_view_succeeded"])
    self.assertTrue(audit["local_inspection"]["list_has_titles"])
    self.assertFalse(audit["local_inspection"]["list_has_graph_connectors"])

    self.assertGreater(audit["explicit_refresh"]["provider_requests"], 0)
    self.assertTrue(audit["explicit_refresh"]["dependency_progress"])
    self.assertTrue(audit["explicit_refresh"]["metadata_progress"])

    direct_edges = {
      tuple(edge) for edge in audit["routing"]["direct_edges"]
    }
    routes = {
      (item["source"], item["target"]): item["kind"]
      for item in audit["routing"]["routes"]
    }
    self.assertIn((145, 216), direct_edges)
    self.assertEqual(routes[(145, 185)], "primary")
    self.assertEqual(routes[(185, 216)], "primary")
    self.assertTrue(routes[(145, 216)].startswith("bypass["))

    self.assertEqual(
      set(audit["selection_lifecycle"]["added_roots"]),
      {"206", "218"},
    )
    self.assertEqual(audit["selection_lifecycle"]["removed_roots"], ["218"])
    self.assertEqual(
      audit["selection_lifecycle"]["remove_provider_requests"],
      0,
    )

  def test_real_provider_lane_evidence_covers_required_stateful_cases(self):
    commands = self.audit()["certification"]["commands"]
    by_command = {
      tuple(item["command"]): item
      for item in commands
    }

    self.assertEqual(
      by_command[("./rwf", "lanes", "select", "63", "65")]["closure"],
      ["63", "65"],
    )
    self.assertEqual(
      by_command[("./rwf", "lanes", "select", "107")]["closure"],
      ["89", "105", "106", "107", "118"],
    )
    self.assertEqual(
      by_command[("./rwf", "lanes", "select", "120", "121")]["closure"],
      ["63", "120", "121"],
    )
    self.assertEqual(
      by_command[("./rwf", "lanes", "select", "205")]["closure"],
      ["205", "208"],
    )

    listing = by_command[("./rwf", "lanes", "list")]["stdout"]
    self.assertIn("✓A.208", listing)

    added = by_command[("./rwf", "lanes", "select", "add", "218")]
    self.assertEqual(added["roots"], ["205", "218"])
    self.assertIn("217", added["closure"])
    self.assertIn("208", added["closure"])

    removed = by_command[
      ("./rwf", "lanes", "select", "remove", "205")
    ]
    self.assertEqual(removed["roots"], ["218"])
    self.assertNotIn("205", removed["closure"])


if __name__ == "__main__":
  unittest.main()
