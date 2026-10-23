"""RWF #702 isolated real-B CLI oracle on verified assembled #703 source.

The only production delta in this diagnostic branch is the exact #702
post-write receipt hunk on existing assembled manual_test_cli.py. This
test retains #703's prior physical-Git acceptance sequence and invokes
the existing native Python entrypoint, including on Windows.
"""
import unittest


class NativeBFailCliProbe(unittest.TestCase):
  def test_shipped_manual_fail_reports_durable_outcome_after_version_bump(self):
    """Legal FAIL should report its own result, even when old SHA is stale."""
    import json
    from pathlib import Path
    import subprocess
    import tempfile
    import os
    import sys

    from repo_workflow.lifecycle_store import LifecycleStore
    from repo_workflow.state_store import WriterIdentity
    from tests.support import RepoFixture

    engine = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory) / "consumer"
      root.mkdir()
      fixture = RepoFixture(root, version="1.0.0-issue.703.5.7")
      fixture._run("switch", "-c", "issue-703-actual-manual")
      catalogue = json.loads((engine / ".ci/tests.json").read_text())
      harness = catalogue["tests"][0]["test-harness"]
      catalogue["tests"].append({
        "test-harness": harness,
        "issue-703-manual--NEGATIVE": {
          "type": "manual",
          "instructions": "Check independent negative path",
          "expected_result": "This manual case deliberately fails",
        },
      })
      (root / ".ci/tests.json").write_text(json.dumps(catalogue))
      candidate = fixture.commit("exact manual case candidate")
      identity = WriterIdentity("certifier-703", "operator-live-local")
      store = LifecycleStore(root)
      start = store.transition(703, "start", None, None, identity, None)
      review = store.transition(
        703, "submit-review", candidate, None, identity, start.revision,
      )
      accepted = store.transition(
        703, "accept", candidate, None, identity, review.revision,
      )
      self.assertEqual(accepted.lifecycle.state, "accepted")
      env = dict(os.environ, RWF_WRITER_ID=identity.writer_id,
                 RWF_SESSION_ID=identity.session_id)

      def cli(*args):
        return subprocess.run(
          [sys.executable, str(engine / "repo_workflow.py"),
           "--root", str(root), *args],
          capture_output=True, text=True, env=env,
        )

      selected = cli("test", "integration", "--manual")
      self.assertEqual(selected.returncode, 0, selected.stderr)
      self.assertIn("issue-703-manual--NEGATIVE", selected.stdout)
      negative = cli("test", "failed")
      self.assertNotEqual(negative.returncode, 0)
      events = (
        root / ".repoworkflow/validation/testResults-703.jsonl"
      ).read_text().splitlines()
      self.assertEqual(len(events), 1)
      self.assertEqual(json.loads(events[0])["result"], "failed")
      self.assertEqual(
        (root / "VERSION").read_text(encoding="utf-8"),
        "1.0.0-issue.703.6.0\n",
      )
      lifecycle = LifecycleStore(root).read(703).lifecycle
      self.assertEqual(lifecycle.state, "active")
      self.assertFalse(lifecycle.dependency_satisfied)
      # RED presentation oracle: the native handler must report the real
      # durable MIT failure rather than a generic post-version stale-SHA
      # readback error.  All above product effects have been checked first.
      self.assertIn("Manual integration FAILED", negative.stdout,
                    negative.stderr)

