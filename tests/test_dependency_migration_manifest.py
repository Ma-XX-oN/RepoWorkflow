from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from repo_workflow.dependency_migration_manifest import (
  DependencyMigrationManifestError,
  load_dependency_migration_manifest,
  validate_dependency_migration_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
  ROOT
  / ".repoworkflow"
  / "migrations"
  / "native-dependencies-v1.json"
)


class DependencyMigrationManifestTests(unittest.TestCase):
  def value(self) -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))

  def test_repository_manifest_is_complete_valid_and_acyclic(self):
    manifest = load_dependency_migration_manifest(MANIFEST)
    self.assertEqual(
      manifest.migration_id,
      "repoworkflow-native-dependencies-v1",
    )
    self.assertEqual(manifest.repository, "Ma-XX-oN/RepoWorkflow")
    self.assertEqual(len(manifest.issues), 171)
    self.assertEqual(
      sum(bool(item.blocked_by) for item in manifest.issues.values()),
      110,
    )
    self.assertEqual(
      sum(len(item.blocked_by) for item in manifest.issues.values()),
      253,
    )
    self.assertEqual(manifest.unresolved, ())

  def test_rejects_unresolved_relationships(self):
    value = self.value()
    value["unresolved"] = [{"issue": 999, "reason": "ambiguous"}]
    with self.assertRaisesRegex(
      DependencyMigrationManifestError,
      "still has unresolved relationships",
    ):
      validate_dependency_migration_manifest(value)

  def test_rejects_self_dependency(self):
    value = self.value()
    value["issues"]["205"]["blocked_by"] = [205]
    with self.assertRaisesRegex(
      DependencyMigrationManifestError,
      "cannot depend on itself",
    ):
      validate_dependency_migration_manifest(value)

  def test_rejects_duplicate_dependency(self):
    value = self.value()
    value["issues"]["205"]["blocked_by"] = [208, 208]
    with self.assertRaisesRegex(
      DependencyMigrationManifestError,
      "duplicate dependency",
    ):
      validate_dependency_migration_manifest(value)

  def test_rejects_unreviewed_dependency_reference(self):
    value = self.value()
    value["issues"]["205"]["blocked_by"] = [999]
    with self.assertRaisesRegex(
      DependencyMigrationManifestError,
      "references unreviewed dependency 999",
    ):
      validate_dependency_migration_manifest(value)

  def test_rejects_cycle(self):
    value = self.value()
    value["issues"]["208"]["blocked_by"] = [205]
    with self.assertRaisesRegex(
      DependencyMigrationManifestError,
      "contains cycle",
    ):
      validate_dependency_migration_manifest(value)

  def test_rejects_dependencies_without_edge_provenance(self):
    value = self.value()
    value["issues"]["205"]["provenance"] = ["reviewed:no-direct-edge"]
    with self.assertRaisesRegex(
      DependencyMigrationManifestError,
      "dependencies without edge provenance",
    ):
      validate_dependency_migration_manifest(value)

  def test_rejects_inconsistent_scope_counts(self):
    value = self.value()
    value["source_snapshot"]["reviewed_issue_count"] -= 1
    with self.assertRaisesRegex(
      DependencyMigrationManifestError,
      "reviewed_issue_count",
    ):
      validate_dependency_migration_manifest(value)

  def test_rejects_excluded_issue_in_reviewed_graph(self):
    value = self.value()
    excluded = value["excluded_issues"][0]["issue"]
    template = copy.deepcopy(value["issues"]["205"])
    template["blocked_by"] = []
    template["provenance"] = ["reviewed:no-direct-edge"]
    value["issues"][str(excluded)] = template
    value["source_snapshot"]["reviewed_issue_count"] += 1
    with self.assertRaisesRegex(
      DependencyMigrationManifestError,
      "excluded issue appears in reviewed issues",
    ):
      validate_dependency_migration_manifest(value)


if __name__ == "__main__":
  unittest.main()
