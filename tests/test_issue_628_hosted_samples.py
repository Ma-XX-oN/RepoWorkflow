"""Replay verified GitHub provider snapshots from 2026-10-09 against #628."""
import base64
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
  "issue628_observer", ROOT / "scripts" / "observe-ci-trigger.py"
)
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)

TEMP_SOURCE = "1cf52daea5405f28711c23fe7361a29ad6c079a6"
REG_SOURCE = "a1632143f4b7ef4a0ea477e7dd508096a8d8336a"
TEMP_ONE = "ddbb99569f790944fed2fa3c8a431e02287e8da4"
TEMP_LOG = "e08bec458d18a89e87f86c552525868d5ddfa9a4"
TEMP_TWO = "b5b61561940270e4cb01c0398d09e147123509b2"
REG_ONE = "1e7db817fbf633362f2e36bdc8ff7b66de735381"
REG_LOG = "4a04dadff0a785e13e75ca89ba0bcf42fb412a4b"
INTEGRATION = "0c5cb0001b8ca8296ec479a687a0df5d118556b6"


def commit(parent, file, message=""):
  return {"parents": [{"sha": parent}], "files": [{"filename": file}],
          "commit": {"message": message}}


# Inputs captured independently from REST commit/file records.  Expected
# tested candidates captured from actual hosted plan-job logs.
COMMITS = {
  TEMP_SOURCE: commit("0" * 40, ".ci/temp-tests.json"),
  TEMP_ONE: commit(TEMP_SOURCE, ".ci/run"),
  TEMP_LOG: commit(
    TEMP_ONE, ".repoworkflow/validation/testResults-541.jsonl",
    "test: publish hosted evidence from run 37997910448",
  ),
  TEMP_TWO: commit(TEMP_LOG, ".ci/run"),
  REG_SOURCE: commit("0" * 40, ".ci/engine-version"),
  REG_ONE: commit(REG_SOURCE, ".ci/run"),
  REG_LOG: commit(
    REG_ONE, ".repoworkflow/validation/testResults-541.jsonl",
    "test: publish hosted evidence from run 37998546029",
  ),
  INTEGRATION: commit(REG_LOG, ".ci/run"),
}
MARKERS = {
  TEMP_ONE: "temp-testing " + TEMP_SOURCE + "\n",
  TEMP_TWO: "temp-testing " + TEMP_LOG + "\n",
  REG_ONE: "regression-testing " + REG_SOURCE + "\n",
  INTEGRATION: "integration-testing " + REG_LOG + "\n",
}
EXPECTED = (
  (TEMP_ONE, TEMP_SOURCE, TEMP_SOURCE, "temp-testing"),
  (TEMP_TWO, TEMP_LOG, TEMP_SOURCE, "temp-testing"),
  (REG_ONE, REG_SOURCE, REG_SOURCE, "regression-testing"),
  (INTEGRATION, REG_LOG, REG_SOURCE, "integration-testing"),
)


class HostedSnapshotTests(unittest.TestCase):
  def fetch(self, path, token):
    if "/commits/" in path:
      sha = path.split("/commits/", 1)[1]
      return COMMITS[sha]
    if "/contents/.ci/run?ref=" in path:
      sha = path.split("?ref=", 1)[1]
      return {
        "encoding": "base64",
        "content": base64.b64encode(MARKERS[sha].encode()).decode(),
      }
    raise AssertionError("unexpected provider endpoint: " + path)

  def test_four_real_hosted_plan_source_identities(self):
    for invocation, prior_tip, tested, stage in EXPECTED:
      with self.subTest(invocation=invocation):
        actual = observer.verify_provider_request(
          "/repos/Ma-XX-oN/RepoWorkflow", invocation, "snapshot", self.fetch,
        )
        self.assertEqual(actual["invocation_sha"], invocation)
        self.assertEqual(actual["previous_tip"], prior_tip)
        self.assertEqual(actual["tested_sha"], tested)
        self.assertEqual(actual["stage"], stage)

  def test_snapshot_contains_four_distinct_invocations(self):
    self.assertEqual(len(COMMITS), 8)
    self.assertEqual(len({row[0] for row in EXPECTED}), 4)


if __name__ == "__main__":
  unittest.main()
