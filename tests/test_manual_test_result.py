"""Deterministic isolated contracts for MIT state and canonical evidence.

Full hosted-provider acceptance is independently owned by issue #703.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import os
import tempfile
import unittest
from unittest import mock

from repo_workflow.manual_test_state import (
  ManualSelectionError, read_active_manual_selection, select_manual_case,
)
from repo_workflow.manual_test_result import (
  FailureHandoff, ManualResultError, reconcile_manual_result, record_manual_result,
  require_manual_completion, read_manual_case_results,
)


@dataclass(frozen=True)
class Case:
  name: str
  definition_digest: str


def _setup(tmp_path):
  subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
  subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.org"], check=True)
  subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Fixture"], check=True)
  (tmp_path / "sample.txt").write_text("original\n")
  subprocess.run(["git", "-C", str(tmp_path), "add", "sample.txt"], check=True)
  subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "fixture"], check=True)
  sha = subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()
  cases = (Case("issue-701-manual--ONE", "a" * 64),
           Case("issue-701-manual--TWO", "b" * 64))
  return tmp_path, sha, cases


def _log(root):
  return root / ".repoworkflow/validation/testResults-701.jsonl"


def _selected(root, sha, cases, index=0):
  return select_manual_case(root, 701, sha, cases[index], cases=cases)


def _record(root, sha, cases, result="succeeded", **extra):
  return record_manual_result(root, 701, sha, result, operator="tester",
                              evidence_ref="fixture://observed", cases=cases, **extra)


class _MonkeyPatch:
  def __init__(self, test):
    self.test = test

  def setattr(self, target, attribute, replacement):
    patcher = mock.patch.object(target, attribute, replacement)
    patcher.start()
    self.test.addCleanup(patcher.stop)

  def setenv(self, key, value):
    patcher = mock.patch.dict(os.environ, {key: value})
    patcher.start()
    self.test.addCleanup(patcher.stop)

  def delenv(self, key, raising=True):
    if key not in os.environ:
      if raising:
        raise KeyError(key)
      return
    previous = os.environ.pop(key)
    self.test.addCleanup(lambda: os.environ.__setitem__(key, previous))


class ManualIntegrationResultTests(unittest.TestCase):
  def setUp(self):
    directory = tempfile.TemporaryDirectory(prefix="rwf-manual-")
    self.addCleanup(directory.cleanup)
    self._fixture = _setup(Path(directory.name))

  def test_absent_and_no_implicit_pass(self):
    root, sha, cases = self._fixture
    assert read_active_manual_selection(root, 701, sha, cases=cases) is None
    with self.assertRaisesRegex(ManualResultError, "exactly one"):
      _record(root, sha, cases)
    assert not _log(root).exists()


  def test_select_pass_consumes_and_reads_canonical_evidence(self):
    root, sha, cases = self._fixture
    chosen = _selected(root, sha, cases)
    assert read_active_manual_selection(root, 701, sha, cases=cases) == chosen
    outcome = _record(root, sha, cases)
    assert outcome.completed and outcome.case == cases[0].name
    assert read_active_manual_selection(root, 701, sha, cases=cases) is None
    event = json.loads(_log(root).read_text())
    assert event["testSHA"] == sha
    assert event["operator"] == "tester"
    assert event["definitionDigest"] == cases[0].definition_digest
    assert event["manualEvidenceId"] == outcome.evidence_id
    with self.assertRaises(ManualResultError):
      require_manual_completion(root, 701, sha, cases=cases)


  def test_complete_only_after_all_cases_pass(self):
    root, sha, cases = self._fixture
    for index in range(len(cases)):
      _selected(root, sha, cases, index)
      if index == 1:
        with self.assertRaisesRegex(ManualResultError, "active"):
          require_manual_completion(root, 701, sha, cases=cases)
      _record(root, sha, cases)
    assert require_manual_completion(root, 701, sha, cases=cases) == tuple(sorted(c.name for c in cases))


  def test_double_active_selection_rejected_no_mutation(self):
    root, sha, cases = self._fixture
    _selected(root, sha, cases)
    path = root / ".repoworkflow/manual/active-701.json"
    raw = json.loads(path.read_text())
    raw["active"].append({**raw["active"][0], "name": cases[1].name})
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    with self.assertRaisesRegex(ManualSelectionError, "multiple"):
      _record(root, sha, cases)
    assert path.read_bytes() == before and not _log(root).exists()


  def test_stale_definition_rejected_no_mutation(self):
    root, sha, cases = self._fixture
    _selected(root, sha, cases)
    updated = (Case(cases[0].name, "c" * 64), cases[1])
    with self.assertRaisesRegex(ManualSelectionError, "stale"):
      _record(root, sha, updated)
    assert not _log(root).exists()


  def test_stale_sha_rejected_no_mutation(self):
    root, sha, cases = self._fixture
    _selected(root, sha, cases)
    (root / "sample.txt").write_text("changed\n")
    subprocess.run(["git", "-C", str(root), "commit", "-qam", "change"], check=True)
    with self.assertRaisesRegex(ManualSelectionError, "current HEAD"):
      _record(root, sha, cases)
    assert not _log(root).exists()


  def test_invalid_manual_name_rejected(self):
    root, sha, cases = self._fixture
    with self.assertRaisesRegex(ManualSelectionError, "invalid manual"):
      _selected(root, sha, (Case("issue-701-automatic--ONE", "a" * 64),))
    assert not _log(root).exists()


  def test_duplicate_active_select_rejected(self):
    root, sha, cases = self._fixture
    _selected(root, sha, cases)
    with self.assertRaisesRegex(ManualSelectionError, "already"):
      _selected(root, sha, cases, 1)
    assert read_active_manual_selection(root, 701, sha, cases=cases).name == cases[0].name


  def test_wrong_issue_selection_rejected(self):
    root, sha, cases = self._fixture
    _selected(root, sha, cases)
    path = root / ".repoworkflow/manual/active-701.json"
    state = json.loads(path.read_text())
    state["active"][0]["issue"] = 700
    path.write_text(json.dumps(state))
    with self.assertRaisesRegex(ManualSelectionError, "stale"):
      _record(root, sha, cases)


  def test_timeout_never_pass_or_fail(self):
    root, sha, cases = self._fixture
    _selected(root, sha, cases)
    with self.assertRaisesRegex(ManualResultError, "TIMEOUT"):
      _record(root, sha, cases, "TIMEOUT")
    assert not _log(root).exists()


  def test_failed_candidate_immutable_and_no_progression(self):
    root, sha, cases = self._fixture
    _selected(root, sha, cases)
    calls = []
    def verified(*args):
      calls.append(args)
      return FailureHandoff("active", False, "1.2.3-issue.701.2.8",
                            "1.2.3-issue.701.3.0", "repair-team")
    out = _record(root, sha, cases, "failed", on_failure=verified)
    assert out.result == "failed" and len(calls) == 1
    with self.assertRaisesRegex(ManualResultError, "MIT FAIL"):
      require_manual_completion(root, 701, sha, cases=cases)
    with self.assertRaisesRegex(ManualSelectionError, "failed candidate"):
      _selected(root, sha, cases, 1)
    assert len(_log(root).read_text().splitlines()) == 1


  def test_failed_handoff_unknown_requires_repair_no_second_append(self):
    root, sha, cases = self._fixture
    _selected(root, sha, cases)
    def fail(*args):
      raise RuntimeError("injected adapter failure after evidence")
    with self.assertRaisesRegex(RuntimeError, "injected"):
      _record(root, sha, cases, "failed", on_failure=fail)
    assert len(_log(root).read_text().splitlines()) == 1
    with self.assertRaisesRegex(ManualSelectionError, "pending"):
      _record(root, sha, cases, "failed", on_failure=fail)
    with self.assertRaisesRegex(ManualResultError, "readback required"):
      reconcile_manual_result(root, 701, sha, cases=cases, on_failure=fail)
    assert len(_log(root).read_text().splitlines()) == 1
    with self.assertRaisesRegex(ManualResultError, "UNKNOWN"):
      require_manual_completion(root, 701, sha, cases=cases)


  def test_success_lost_ack_readback_no_duplicate(self):
    monkeypatch = _MonkeyPatch(self)
    root, sha, cases = self._fixture
    _selected(root, sha, cases)
    import repo_workflow.manual_test_result as implementation
    original = implementation._consume
    count = [0]
    def interrupted(path):
      count[0] += 1
      if count[0] == 1:
        raise OSError("simulated crash after append")
      original(path)
    monkeypatch.setattr(implementation, "_consume", interrupted)
    with self.assertRaises(OSError):
      _record(root, sha, cases)
    out = reconcile_manual_result(root, 701, sha, cases=cases)
    assert out.completed
    assert len(_log(root).read_text().splitlines()) == 1


  def test_corrupt_log_unknown_rejects_progression(self):
    root, sha, cases = self._fixture
    _selected(root, sha, cases)
    _log(root).parent.mkdir(parents=True, exist_ok=True)
    _log(root).write_text("{unclosed\n")
    with self.assertRaisesRegex(ManualResultError, "UNKNOWN"):
      _record(root, sha, cases)
    assert _log(root).read_text() == "{unclosed\n"


  def test_invalid_operator_does_not_mutate(self):
    root, sha, cases = self._fixture
    _selected(root, sha, cases)
    with self.assertRaisesRegex(ManualResultError, "operator"):
      record_manual_result(root, 701, sha, "succeeded", operator=" ",
                           evidence_ref="evidence", cases=cases)
    assert not _log(root).exists()


  def test_lock_contention_fails_closed(self):
    root, sha, cases = self._fixture
    path = root / ".repoworkflow/manual/lock-701"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    with self.assertRaisesRegex(ManualSelectionError, "locked"):
      _selected(root, sha, cases)
    assert not _log(root).exists()


  def test_failed_handoff_invalid_does_not_fabricate_completion(self):
    root, sha, cases = self._fixture
    _selected(root, sha, cases)
    with self.assertRaisesRegex(ManualResultError, "no verified"):
      _record(root, sha, cases, "failed", on_failure=lambda *args: None)
    assert len(_log(root).read_text().splitlines()) == 1
    with self.assertRaisesRegex(ManualResultError, "UNKNOWN"):
      require_manual_completion(root, 701, sha, cases=cases)


  def test_failed_handoff_requires_q_plus_one_r_zero(self):
    root, sha, cases = self._fixture
    _selected(root, sha, cases)
    def wrong(*args):
      return FailureHandoff("active", False, "1.2.3-issue.701.2.8",
                            "1.2.3-issue.701.3.1", "repair-team")
    with self.assertRaisesRegex(ManualResultError, "contract rejected"):
      _record(root, sha, cases, "failed", on_failure=wrong)
    with self.assertRaisesRegex(ManualResultError, "UNKNOWN"):
      require_manual_completion(root, 701, sha, cases=cases)


  def test_uncommitted_source_change_rejects_candidate(self):
    root, sha, cases = self._fixture
    _selected(root, sha, cases)
    (root / "sample.txt").write_text("uncommitted change\n")
    with self.assertRaisesRegex(ManualSelectionError, "changed source inputs"):
      _record(root, sha, cases)
    assert not _log(root).exists()


  def test_old_pass_cannot_authorize_new_source_sha(self):
    root, sha, cases = self._fixture
    _selected(root, sha, cases)
    _record(root, sha, cases)
    (root / "sample.txt").write_text("second candidate\n")
    subprocess.run(["git", "-C", str(root), "commit", "-qam", "second"], check=True)
    new_sha = subprocess.check_output(
      ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    with self.assertRaisesRegex(ManualResultError, "incomplete"):
      require_manual_completion(root, 701, new_sha, cases=cases)


  def test_old_pass_cannot_authorize_new_definition_digest(self):
    root, sha, cases = self._fixture
    for index in range(2):
      _selected(root, sha, cases, index)
      _record(root, sha, cases)
    changed = (Case(cases[0].name, "f" * 64), cases[1])
    with self.assertRaisesRegex(ManualResultError, "incomplete"):
      require_manual_completion(root, 701, sha, cases=changed)


  def test_mit_fail_after_int_preparation_does_not_advance_sha(self):
    root, sha, cases = self._fixture
    (root / ".ci").mkdir()
    marker = root / ".ci/run"
    marker.write_text("integration-testing " + sha + "\n")
    subprocess.run(["git", "-C", str(root), "add", ".ci/run"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "prepared"], check=True)
    prepared_sha = subprocess.check_output(
      ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    _selected(root, prepared_sha, cases)
    def handoff(*args):
      return FailureHandoff("active", False, "1.2.3-issue.701.2.1",
                            "1.2.3-issue.701.3.0", "repair-owner")
    _record(root, prepared_sha, cases, "failed", on_failure=handoff)
    assert subprocess.check_output(
      ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip() == prepared_sha
    assert marker.read_text() == "integration-testing " + sha + "\n"
    with self.assertRaisesRegex(ManualResultError, "MIT FAIL"):
      require_manual_completion(root, 701, prepared_sha, cases=cases)


  def test_result_read_model_and_no_stale_pass(self):
    root, sha, cases = self._fixture
    _selected(root, sha, cases)
    _record(root, sha, cases)
    assert read_manual_case_results(root, 701, sha, cases=cases) == {
      cases[0].name: "succeeded",
    }
    changed = (Case(cases[0].name, "c" * 64), cases[1])
    assert read_manual_case_results(root, 701, sha, cases=changed) == {}


  def test_cli_identity_env_and_local_evidence_ref(self):
    monkeypatch = _MonkeyPatch(self)
    root, sha, cases = self._fixture
    monkeypatch.setenv("RWF_WRITER_ID", "known-operator")
    _selected(root, sha, cases)
    out = record_manual_result(root, 701, sha, "succeeded", cases=cases)
    entry = json.loads(_log(root).read_text())
    assert entry["operator"] == "known-operator"
    assert entry["evidenceRef"].endswith(out.evidence_id)
    assert entry["evidenceRef"].startswith(".repoworkflow/validation/testResults-701.jsonl")


  def test_cli_no_identity_rejected(self):
    monkeypatch = _MonkeyPatch(self)
    root, sha, cases = self._fixture
    monkeypatch.delenv("RWF_WRITER_ID", raising=False)
    _selected(root, sha, cases)
    with self.assertRaisesRegex(ManualResultError, "operator identity"):
      record_manual_result(root, 701, sha, "succeeded", cases=cases)
    assert not _log(root).exists()


  def test_terminal_pass_cannot_be_reselected_directly(self):
    root, sha, cases = self._fixture
    _selected(root, sha, cases)
    _record(root, sha, cases)
    with self.assertRaisesRegex(ManualSelectionError, "recorded terminal"):
      _selected(root, sha, cases)
    assert len(_log(root).read_text().splitlines()) == 1


  def test_real_lifecycle_store_reject_after_manual_failure(self):
    from repo_workflow.lifecycle_store import LifecycleStore
    from repo_workflow.state_store import WriterIdentity

    root, sha, cases = self._fixture
    store = LifecycleStore(root)
    writer = WriterIdentity("worker-701", "lifecycle-session")
    started = store.transition(701, "start", None, None, writer, None)
    review = store.transition(
      701, "submit-review", sha, None, writer, started.revision,
    )
    accepted = store.transition(
      701, "accept", sha, None, writer, review.revision,
    )
    assert accepted.lifecycle.state == "accepted"
    assert not accepted.lifecycle.dependency_satisfied

    _selected(root, sha, cases)

    def canonical_reject(path, issue, candidate):
      before = store.read(issue)
      assert before.lifecycle.state == "accepted"
      after = store.transition(
        issue, "reject/reopen", candidate, None, writer, before.revision,
      )
      assert after.lifecycle.state == "active"
      assert after.lifecycle.history[-1].transition == "reject/reopen"
      return FailureHandoff(
        "active", False, "1.2.3-issue.701.5.9",
        "1.2.3-issue.701.6.0", "repair-team",
      )

    outcome = _record(root, sha, cases, "failed", on_failure=canonical_reject)
    assert outcome.result == "failed"
    persisted = LifecycleStore(root).read(701).lifecycle
    assert persisted.state == "active"
    assert not persisted.dependency_satisfied
    assert persisted.history[-1].transition == "reject/reopen"
    with self.assertRaisesRegex(ManualResultError, "MIT FAIL"):
      require_manual_completion(root, 701, sha, cases=cases)
    with self.assertRaisesRegex(ManualSelectionError, "failed candidate"):
      _selected(root, sha, cases, 1)


  def test_legitimate_lifecycle_state_allowed_not_arbitrary_worktree(self):
    root, sha, cases = self._fixture
    state = root / ".repoworkflow/state"
    state.mkdir(parents=True)
    (state / "legitimate.json").write_text("{}\n")
    _selected(root, sha, cases)
    (root / ".repoworkflow/unrelated.txt").write_text("dirty\n")
    with self.assertRaisesRegex(ManualSelectionError, "changed source inputs"):
      _record(root, sha, cases)
    assert not _log(root).exists()
