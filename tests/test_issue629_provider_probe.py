"""Read-only live-provider probes for #629; never infer assembled PASS.

Opt-in env:
  RWF_629_PROVIDER_RUN_ID: authoritative GitHub Actions run ID
  RWF_629_PROVIDER_HEAD_SHA: 40-character invocation commit
  RWF_629_PROVIDER_ARTIFACT_NAME: expected immutable artifact name
  GITHUB_TOKEN: optional API token (public metadata also readable anonymously)
No mutation, workflow dispatch, or test-minute consumption occurs here.
"""

import json
import os
import re
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API = "https://api.github.com/repos/Ma-XX-oN/RepoWorkflow"


def read_provider(path):
  token = os.environ.get("GITHUB_TOKEN")
  headers = {"Accept": "application/vnd.github+json",
             "X-GitHub-Api-Version": "2022-11-28",
             "User-Agent": "rwf-629-independent-verification"}
  if token:
    headers["Authorization"] = f"Bearer {token}"
  req = Request(API + path, headers=headers)
  with urlopen(req, timeout=15) as response:
    return json.load(response)


class LiveProviderMetadataTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    raw = os.getenv("RWF_629_PROVIDER_RUN_ID", "")
    sha = os.getenv("RWF_629_PROVIDER_HEAD_SHA", "")
    artifact = os.getenv("RWF_629_PROVIDER_ARTIFACT_NAME", "")
    if not (raw and sha and artifact):
      raise unittest.SkipTest(
        "PENDING provider-only: real run, invocation SHA and artifact not configured")
    if not raw.isdecimal() or int(raw) <= 0 or not re.fullmatch(
        r"[0-9a-fA-F]{40}", sha):
      raise AssertionError("Invalid authoritative provider run identity")
    cls.run_id = int(raw)
    cls.expected_sha = sha.lower()
    cls.expected_artifact = artifact

  def test_completed_successful_run_exact_invocation_sha(self):
    try:
      run = read_provider(f"/actions/runs/{self.run_id}")
    except (HTTPError, URLError, OSError) as exc:
      self.fail(f"Provider lookup unavailable: {exc}")
    self.assertEqual(type(run.get("id")), int)
    self.assertEqual(run["id"], self.run_id)
    self.assertEqual(run.get("head_sha"), self.expected_sha)
    self.assertEqual(run.get("status"), "completed")
    self.assertEqual(run.get("conclusion"), "success")

  def test_provider_run_has_named_unexpired_artifact(self):
    try:
      listing = read_provider(f"/actions/runs/{self.run_id}/artifacts?per_page=100")
    except (HTTPError, URLError, OSError) as exc:
      self.fail(f"Provider artifact lookup unavailable: {exc}")
    entries = listing.get("artifacts", [])
    matching = [a for a in entries if a.get("name") == self.expected_artifact]
    self.assertEqual(len(matching), 1)
    artifact = matching[0]
    self.assertEqual(type(artifact.get("id")), int)
    self.assertGreater(artifact["id"], 0)
    self.assertFalse(artifact.get("expired", True))
    self.assertGreater(artifact.get("size_in_bytes", 0), 0)


if __name__ == "__main__":
  unittest.main()
