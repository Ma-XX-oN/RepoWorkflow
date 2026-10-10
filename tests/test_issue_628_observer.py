"""Contract tests for the read-only GitHub-hosted #628 observer."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
  "issue628_observer", ROOT / "scripts" / "observe-ci-trigger.py"
)
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class ObserverTests(unittest.TestCase):
  def setUp(self):
    self.begin = "2026-10-10T18:00:00Z"
    self.end = "2026-10-10T18:01:00Z"
    self.calls = []

  def fake(self, path, token):
    self.calls.append(path)
    if path.endswith("/workflows/on-demand-ci.yml"):
      return {"id": 991, "state": "active"}
    if "/runs?" in path:
      return {"workflow_runs": []}
    raise AssertionError("unexpected provider path " + path)

  def invoke(self, fetch=None):
    return observer.observe(
      "example/repo", "on-demand-ci.yml", "issue-628-example",
      self.begin, self.end, "test-token", fetch or self.fake,
    )

  def test_negative_requires_active_registered_workflow(self):
    def inactive(path, token):
      return {"id": 991, "state": "disabled_manually"}
    with self.assertRaisesRegex(observer.ObservationError, "not active"):
      self.invoke(inactive)

  def test_missing_workflow_provider_error_is_not_zero(self):
    def missing(path, token):
      raise observer.ObservationError("404 not found")
    with self.assertRaisesRegex(observer.ObservationError, "404"):
      self.invoke(missing)

  def test_completed_window_zero_runs(self):
    report = self.invoke()
    self.assertEqual((report["run_count"], report["job_count"]), (0, 0))
    self.assertEqual(report["workflow_id"], 991)
    self.assertTrue(any("branch=issue-628-example" in p for p in self.calls))

  def test_pending_window_cannot_certify_zero(self):
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    with self.assertRaisesRegex(observer.ObservationError, "not ended"):
      observer.observe("example/repo", "on-demand-ci.yml",
                       "issue-628-example", self.begin, future, "token",
                       self.fake)

  def test_timezone_required(self):
    with self.assertRaisesRegex(observer.ObservationError, "offset"):
      observer.utc("2026-10-10T18:00:00")

  def test_reversed_window_rejected(self):
    with self.assertRaisesRegex(observer.ObservationError, "reversed"):
      observer.observe("example/repo", "on-demand-ci.yml",
                       "issue-628-example", self.end, self.begin, "token",
                       self.fake)

  def test_valid_run_jobs_and_exact_candidate_sha_recorded(self):
    def response(path, token):
      if path.endswith("/workflows/on-demand-ci.yml"):
        return {"id": 991, "state": "active"}
      if "/runs?" in path:
        return {"workflow_runs": [{
          "id": 88, "event": "push", "head_branch": "issue-628-example",
          "head_sha": "a" * 40, "status": "completed",
          "created_at": "2026-10-10T18:00:10Z",
          "html_url": "https://github.com/example/repo/actions/runs/88",
          "conclusion": "success",
        }]}
      return {"jobs": [{"id": 9, "name": "validate",
                        "conclusion": "success"}]}
    report = self.invoke(response)
    self.assertEqual((report["run_count"], report["job_count"]), (1, 1))
    self.assertEqual(report["runs"][0]["head_sha"], "a" * 40)

  def test_incomplete_run_rejected(self):
    def pending(path, token):
      if path.endswith("/workflows/on-demand-ci.yml"):
        return {"id": 991, "state": "active"}
      return {"workflow_runs": [{
        "id": 1, "event": "push", "head_branch": "issue-628-example",
        "created_at": "2026-10-10T18:00:10Z", "status": "in_progress",
      }]}
    with self.assertRaisesRegex(observer.ObservationError, "pending"):
      self.invoke(pending)

  def test_mismatched_ref_rejected(self):
    def wrong(path, token):
      if path.endswith("/workflows/on-demand-ci.yml"):
        return {"id": 991, "state": "active"}
      return {"workflow_runs": [{
        "id": 1, "event": "push", "head_branch": "main",
        "created_at": "2026-10-10T18:00:10Z", "status": "completed",
      }]}
    with self.assertRaisesRegex(observer.ObservationError, "mismatched"):
      self.invoke(wrong)

  def test_pagination_fails_closed_if_nonterminating(self):
    def saturated(path, token):
      return {"workflow_runs": [{} for _ in range(100)]}
    with self.assertRaisesRegex(observer.ObservationError, "not exhausted"):
      observer.all_pages("/x", "workflow_runs", "token", saturated)

  def test_provider_schema_without_runs_rejected(self):
    with self.assertRaisesRegex(observer.ObservationError, "missing"):
      observer.all_pages("/x", "workflow_runs", "token",
                         lambda path, token: {})


if __name__ == "__main__":
  unittest.main()
