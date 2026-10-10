"""Real-provider coverage for #110; run against an exact candidate checkout."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.state_store import WriterIdentity
from repo_workflow.validation_coverage import Requirement
from repo_workflow.validation_plan import execute_from_store
from repo_workflow.validation_store import ValidationEvidenceStore, ValidationObservation


ROOT = Path(__file__).resolve().parents[1]


class ProviderLiveAcceptance(unittest.TestCase):
  def test_imported_pass_skips_redundant_stage(self):
    head = subprocess.run(
      ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
      check=True, text=True,
    ).stdout.strip()
    with tempfile.TemporaryDirectory() as tmp:
      store = ValidationEvidenceStore(Path(tmp))
      record = ValidationObservation(
        record_id="trusted-local", candidate_sha=head,
        version="0.1.1", branch="issue-110", unit="reuse",
        fingerprint="a" * 64, verdict="PASS", mode="automated",
        runner="python-3.13", platform="linux", provider_run="local/1",
      )
      store.publish(record, WriterIdentity("tester", "run"))
      request = {
        "contract_version": 1, "operation": "execute",
        "invocation_id": "provider-live-110",
        "candidate": {
          "repository": "owner/repo", "commit": head, "base": "b" * 40,
        },
        "requirements": {
          "stages": [], "capabilities": [], "artifacts": [],
        },
        "inputs": {"base": "b" * 40},
      }
      plan, result = execute_from_store(
        ROOT, store, [
          Requirement("reuse", "a" * 64),
          Requirement("missing", "c" * 64),
        ], head, request,
        {"missing": "invariant-self-ci-contract"},
        trusted_record_ids=frozenset({"trusted-local"}),
        equivalent_candidate_shas=frozenset(),
      )
      self.assertEqual(plan.automated_units, ("missing",))
      self.assertEqual(result["reused"], ("reuse",))
      self.assertEqual(result["executed"], ("missing",))
      self.assertEqual(result["observations"][0]["outcome"], "succeeded")


if __name__ == "__main__":
  unittest.main()
