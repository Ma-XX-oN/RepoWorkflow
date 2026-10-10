"""Contract tests for the read-only GitHub-hosted #628 observer."""
import base64
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
      if "/commits/" in path:
        return {"parents": [{"sha": "b" * 40}],
                "files": [{"filename": ".ci/run"}]}
      if "/contents/.ci/run" in path:
        marker = "regression-testing " + "b" * 40 + "\n"
        return {"encoding": "base64",
                "content": base64.b64encode(marker.encode()).decode()}
      return {"jobs": [{"id": 9, "name": "validate",
                        "conclusion": "success"}]}
    report = self.invoke(response)
    self.assertEqual((report["run_count"], report["job_count"]), (1, 1))
    self.assertEqual(report["runs"][0]["invocation_sha"], "a" * 40)
    self.assertEqual(report["runs"][0]["tested_sha"], "b" * 40)
    self.assertEqual(report["executed_test_job_count"], 1)

  def test_provider_commit_rejects_mixed_change(self):
    def mixed(path, token):
      return {"parents": [{"sha": "b" * 40}],
              "files": [{"filename": ".ci/run"}, {"filename": "source"}]}
    with self.assertRaisesRegex(observer.ObservationError, "dedicated"):
      observer.verify_provider_request("/repos/example/repo",
                                       "a" * 40, "token", mixed)

  def test_provider_commit_rejects_merge(self):
    def merge(path, token):
      return {"parents": [{"sha": "b" * 40}, {"sha": "c" * 40}],
              "files": [{"filename": ".ci/run"}]}
    with self.assertRaisesRegex(observer.ObservationError, "single-parent"):
      observer.verify_provider_request("/repos/example/repo",
                                       "a" * 40, "token", merge)

  def test_provider_marker_rejects_stale_candidate(self):
    def stale(path, token):
      if "/commits/" in path:
        return {"parents": [{"sha": "b" * 40}],
                "files": [{"filename": ".ci/run"}]}
      return {"encoding": "base64", "content": base64.b64encode(
        ("regression-testing " + "c" * 40 + "\n").encode()).decode()}
    with self.assertRaisesRegex(observer.ObservationError, "candidate SHA"):
      observer.verify_provider_request("/repos/example/repo",
                                       "a" * 40, "token", stale)

  def test_provider_marker_rejects_tamper(self):
    def tampered(path, token):
      if "/commits/" in path:
        return {"parents": [{"sha": "b" * 40}],
                "files": [{"filename": ".ci/run"}]}
      return {"encoding": "base64", "content": base64.b64encode(
        b"RED-testing wrong\n").decode()}
    with self.assertRaisesRegex(observer.ObservationError, "invalid committed"):
      observer.verify_provider_request("/repos/example/repo",
                                       "a" * 40, "token", tampered)

  def test_duplicate_hosted_run_same_invocation_rejected(self):
    def duplicate(path, token):
      if path.endswith("/workflows/on-demand-ci.yml"):
        return {"id": 991, "state": "active"}
      if "/runs?" in path:
        common = {
          "event": "push", "head_branch": "issue-628-example",
          "head_sha": "a" * 40, "status": "completed",
          "conclusion": "success",
          "created_at": "2026-10-10T18:00:10Z",
          "html_url": "https://github.com/example/repo/actions/runs/1",
        }
        return {"workflow_runs": [dict(common, id=1), dict(common, id=2)]}
      if "/commits/" in path:
        return {"parents": [{"sha": "b" * 40}],
                "files": [{"filename": ".ci/run"}]}
      if "/contents/.ci/run" in path:
        return {"encoding": "base64", "content": base64.b64encode(
          ("regression-testing " + "b" * 40 + "\n").encode()).decode()}
      return {"jobs": [{"id": 9, "name": "validate",
                        "conclusion": "success"}]}
    with self.assertRaisesRegex(observer.ObservationError, "duplicate"):
      self.invoke(duplicate)

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
