"""Deterministic isolated contracts for MIT state and canonical evidence.

Full hosted-provider acceptance is independently owned by issue #703.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import pytest

from repo_workflow.manual_test_state import (
  ManualSelectionError, read_active_manual_selection, select_manual_case,
)
from repo_workflow.manual_test_result import (
  FailureHandoff, ManualResultError, reconcile_manual_result, record_manual_result,
  require_manual_completion,
)


@dataclass(frozen=True)
class Case:
  name: str
  definition_digest: str


@pytest.fixture
def setup(tmp_path):
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


def test_absent_and_no_implicit_pass(setup):
  root, sha, cases = setup
  assert read_active_manual_selection(root, 701, sha, cases=cases) is None
  with pytest.raises(ManualResultError, match="exactly one"):
    _record(root, sha, cases)
  assert not _log(root).exists()


def test_select_pass_consumes_and_reads_canonical_evidence(setup):
  root, sha, cases = setup
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
  with pytest.raises(ManualResultError):
    require_manual_completion(root, 701, sha, cases=cases)


def test_complete_only_after_all_cases_pass(setup):
  root, sha, cases = setup
  for index in range(len(cases)):
    _selected(root, sha, cases, index)
    if index == 1:
      with pytest.raises(ManualResultError, match="active"):
        require_manual_completion(root, 701, sha, cases=cases)
    _record(root, sha, cases)
  assert require_manual_completion(root, 701, sha, cases=cases) == tuple(sorted(c.name for c in cases))


def test_double_active_selection_rejected_no_mutation(setup):
  root, sha, cases = setup
  _selected(root, sha, cases)
  path = root / ".repoworkflow/manual/active-701.json"
  raw = json.loads(path.read_text())
  raw["active"].append({**raw["active"][0], "name": cases[1].name})
  path.write_text(json.dumps(raw))
  before = path.read_bytes()
  with pytest.raises(ManualSelectionError, match="multiple"):
    _record(root, sha, cases)
  assert path.read_bytes() == before and not _log(root).exists()


def test_stale_definition_rejected_no_mutation(setup):
  root, sha, cases = setup
  _selected(root, sha, cases)
  updated = (Case(cases[0].name, "c" * 64), cases[1])
  with pytest.raises(ManualSelectionError, match="stale"):
    _record(root, sha, updated)
  assert not _log(root).exists()


def test_stale_sha_rejected_no_mutation(setup):
  root, sha, cases = setup
  _selected(root, sha, cases)
  (root / "sample.txt").write_text("changed\n")
  subprocess.run(["git", "-C", str(root), "commit", "-qam", "change"], check=True)
  with pytest.raises(ManualSelectionError, match="current HEAD"):
    _record(root, sha, cases)
  assert not _log(root).exists()


def test_invalid_manual_name_rejected(setup):
  root, sha, cases = setup
  with pytest.raises(ManualSelectionError, match="invalid manual"):
    _selected(root, sha, (Case("issue-701-automatic--ONE", "a" * 64),))
  assert not _log(root).exists()


def test_duplicate_active_select_rejected(setup):
  root, sha, cases = setup
  _selected(root, sha, cases)
  with pytest.raises(ManualSelectionError, match="already"):
    _selected(root, sha, cases, 1)
  assert read_active_manual_selection(root, 701, sha, cases=cases).name == cases[0].name


def test_wrong_issue_selection_rejected(setup):
  root, sha, cases = setup
  _selected(root, sha, cases)
  path = root / ".repoworkflow/manual/active-701.json"
  state = json.loads(path.read_text())
  state["active"][0]["issue"] = 700
  path.write_text(json.dumps(state))
  with pytest.raises(ManualSelectionError, match="stale"):
    _record(root, sha, cases)


def test_timeout_never_pass_or_fail(setup):
  root, sha, cases = setup
  _selected(root, sha, cases)
  with pytest.raises(ManualResultError, match="TIMEOUT"):
    _record(root, sha, cases, "TIMEOUT")
  assert not _log(root).exists()


def test_failed_candidate_immutable_and_no_progression(setup):
  root, sha, cases = setup
  _selected(root, sha, cases)
  calls = []
  def verified(*args):
    calls.append(args)
    return FailureHandoff("active", False, "1.2.3-issue.701.2.8",
                          "1.2.3-issue.701.3.0", "repair-team")
  out = _record(root, sha, cases, "failed", on_failure=verified)
  assert out.result == "failed" and len(calls) == 1
  with pytest.raises(ManualResultError, match="MIT FAIL"):
    require_manual_completion(root, 701, sha, cases=cases)
  with pytest.raises(ManualSelectionError, match="failed candidate"):
    _selected(root, sha, cases, 1)
  assert len(_log(root).read_text().splitlines()) == 1


def test_failed_handoff_unknown_requires_repair_no_second_append(setup):
  root, sha, cases = setup
  _selected(root, sha, cases)
  def fail(*args):
    raise RuntimeError("injected adapter failure after evidence")
  with pytest.raises(RuntimeError, match="injected"):
    _record(root, sha, cases, "failed", on_failure=fail)
  assert len(_log(root).read_text().splitlines()) == 1
  with pytest.raises(ManualSelectionError, match="pending"):
    _record(root, sha, cases, "failed", on_failure=fail)
  with pytest.raises(ManualResultError, match="readback required"):
    reconcile_manual_result(root, 701, sha, cases=cases, on_failure=fail)
  assert len(_log(root).read_text().splitlines()) == 1
  with pytest.raises(ManualResultError, match="UNKNOWN"):
    require_manual_completion(root, 701, sha, cases=cases)


def test_success_lost_ack_readback_no_duplicate(setup, monkeypatch):
  root, sha, cases = setup
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
  with pytest.raises(OSError):
    _record(root, sha, cases)
  out = reconcile_manual_result(root, 701, sha, cases=cases)
  assert out.completed
  assert len(_log(root).read_text().splitlines()) == 1


def test_corrupt_log_unknown_rejects_progression(setup):
  root, sha, cases = setup
  _selected(root, sha, cases)
  _log(root).parent.mkdir(parents=True, exist_ok=True)
  _log(root).write_text("{unclosed\n")
  with pytest.raises(ManualResultError, match="UNKNOWN"):
    _record(root, sha, cases)
  assert _log(root).read_text() == "{unclosed\n"


def test_invalid_operator_does_not_mutate(setup):
  root, sha, cases = setup
  _selected(root, sha, cases)
  with pytest.raises(ManualResultError, match="operator"):
    record_manual_result(root, 701, sha, "succeeded", operator=" ",
                         evidence_ref="evidence", cases=cases)
  assert not _log(root).exists()


def test_lock_contention_fails_closed(setup):
  root, sha, cases = setup
  path = root / ".repoworkflow/manual/lock-701"
  path.parent.mkdir(parents=True, exist_ok=True)
  path.touch()
  with pytest.raises(ManualSelectionError, match="locked"):
    _selected(root, sha, cases)
  assert not _log(root).exists()


def test_failed_handoff_invalid_does_not_fabricate_completion(setup):
  root, sha, cases = setup
  _selected(root, sha, cases)
  with pytest.raises(ManualResultError, match="no verified"):
    _record(root, sha, cases, "failed", on_failure=lambda *args: None)
  assert len(_log(root).read_text().splitlines()) == 1
  with pytest.raises(ManualResultError, match="UNKNOWN"):
    require_manual_completion(root, 701, sha, cases=cases)


def test_failed_handoff_requires_q_plus_one_r_zero(setup):
  root, sha, cases = setup
  _selected(root, sha, cases)
  def wrong(*args):
    return FailureHandoff("active", False, "1.2.3-issue.701.2.8",
                          "1.2.3-issue.701.3.1", "repair-team")
  with pytest.raises(ManualResultError, match="contract rejected"):
    _record(root, sha, cases, "failed", on_failure=wrong)
  with pytest.raises(ManualResultError, match="UNKNOWN"):
    require_manual_completion(root, 701, sha, cases=cases)


def test_uncommitted_source_change_rejects_candidate(setup):
  root, sha, cases = setup
  _selected(root, sha, cases)
  (root / "sample.txt").write_text("uncommitted change\n")
  with pytest.raises(ManualSelectionError, match="changed source inputs"):
    _record(root, sha, cases)
  assert not _log(root).exists()
