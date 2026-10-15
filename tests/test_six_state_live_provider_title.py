"""Authenticated provider-title merge acceptance for #583 P12.

Only runs when a hosted GitHub token is available. It does not modify
GitHub issues or repository refs; the merge writes solely to a temp repo.
"""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.lifecycle_store import LifecycleStore
from repo_workflow.repo_info_adapter import issue_info, resolve_info_config
from repo_workflow.state_store import WriterIdentity
from repo_workflow.ticket_merge import merge_ticket_csv
from tests.support import RepoFixture


@unittest.skipUnless(
  os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN"),
  "authenticated GitHub provider token is required",
)
class LiveProviderTitleMergeAcceptance(unittest.TestCase):
  def test_real_provider_title_wins_without_rewriting_lifecycle(self):
    # P12: actual provider source, not a mocked title, is authoritative.
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory) / "repo"
      root.mkdir()
      RepoFixture(root)
      subprocess.run(
        ["git", "remote", "add", "origin",
         "https://github.com/Ma-XX-oN/RepoWorkflow.git"],
        cwd=root, capture_output=True, check=True,
      )
      config = resolve_info_config(root)
      observed = issue_info(root, config, 583)
      self.assertEqual(observed["number"], 583)
      self.assertTrue(observed["title"])

      writer = WriterIdentity("live-verifier", "independent-583")
      life = LifecycleStore(root)
      snapshot = life.transition(
        583, "start", "p12-candidate", 0, writer, None,
      )
      record = root / ".repoworkflow/state/issues/583/lifecycle.json"
      before = record.read_bytes()
      base = (
        "issue,title,dependencies,state,state_revision\n"
        "583,Previously cached,,active,0\n"
      )
      ours = base.replace("Previously cached", "Local divergent title")
      theirs = base.replace("Previously cached", "Other divergent title")
      result = merge_ticket_csv(root, base, ours, theirs)
      self.assertEqual(
        result,
        "issue,title,dependencies,state,state_revision\n"
        f"583,{observed['title']},,active,0\n",
      )
      self.assertEqual(record.read_bytes(), before)
      self.assertEqual(LifecycleStore(root).read(583), snapshot)
      self.assertEqual(snapshot.lifecycle.state, "active")
      self.assertEqual(snapshot.revision, 0)


if __name__ == "__main__":
  unittest.main()
