"""RWF #702: shipped launcher with isolated A/B API fakes, never provider evidence."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.manual_test_cli import after_automatic_integration


SOURCE = Path(__file__).resolve().parents[1]
CATALOGUE_STUB = '''
from dataclasses import dataclass
import json

@dataclass(frozen=True)
class ManualCase:
  name: str
  instructions: str
  expected_result: str
  definition_digest: str

def read_manual_cases(root, issue):
  path = root / ".manual-cases.json"
  rows = json.loads(path.read_text()) if path.exists() else []
  return tuple(sorted(
    (ManualCase(**row) for row in rows if row["name"].startswith(
      "issue-" + str(issue) + "-manual--"
    )), key=lambda case: case.name
  ))
'''
RESULT_STUB = '''
import json
from pathlib import Path

def _selection(root):
  return root / ".manual-active.json"

def _results(root):
  return root / ".manual-results.json"

def read_manual_case_results(root, issue, candidate_sha, *, cases=None):
  pending = root / '.repoworkflow' / 'manual' / ('pending-' + str(issue) + '.json')
  if pending.exists():
    raise ValueError('manual outcome UNKNOWN; reconcile before use')
  if (root / '.version-bumped-by-fail').exists():
    raise ValueError('manual candidate has changed source inputs')
  path = _results(root)
  if not path.exists():
    return {}
  entries = json.loads(path.read_text())
  return entries.get(candidate_sha, {})

def select_manual_case(root, issue, candidate_sha, case):
  data = {
    "name": case.name,
    "issue": issue,
    "sha": candidate_sha,
    "definition_digest": case.definition_digest,
  }
  _selection(root).write_text(json.dumps(data))

def read_active_manual_selection(root, issue, candidate_sha):
  path = _selection(root)
  if not path.exists():
    return None
  data = json.loads(path.read_text())
  if isinstance(data, list):
    return data
  if data["issue"] != issue or data["sha"] != candidate_sha:
    return None
  return data

def record_manual_result(root, issue, candidate_sha, result, *, operator, evidence_ref):
  selected = read_active_manual_selection(root, issue, candidate_sha)
  assert selected is not None
  records = read_manual_case_results(root, issue, candidate_sha)
  assert selected["name"] not in records
  path = _results(root)
  aggregate = json.loads(path.read_text()) if path.exists() else {}
  aggregate.setdefault(candidate_sha, {})[selected["name"]] = result
  path.write_text(json.dumps(aggregate))
  log = root / ".repoworkflow" / "validation" / (
    "testResults-" + str(issue) + ".jsonl"
  )
  log.parent.mkdir(parents=True, exist_ok=True)
  evidence = {
    "kind": "manual-integration", "runner": "operator-fixture",
    "testSHA": candidate_sha, "result": result, "manualCase": selected["name"],
    "definitionDigest": selected["definition_digest"],
    "operator": operator, "evidenceRef": evidence_ref,
  }
  with log.open("a") as handle:
    handle.write(json.dumps(evidence) + "\\n")
  path = _selection(root)
  path.unlink()
  if result == 'failed' and (root / '.simulate-fail-version').exists():
    (root / 'VERSION').write_text('1.2.3-issue.702.0' + chr(10))
    (root / '.version-bumped-by-fail').write_text('1')
    from types import SimpleNamespace
    return SimpleNamespace(
      case=selected['name'], candidate_sha=candidate_sha, result=result,
      evidence_id='fixture-durable-id', evidence_path=str(log), completed=True,
    )
  if result == 'failed' and (root / '.simulate-unknown').exists():
    pending = root / '.repoworkflow' / 'manual' / (
      'pending-' + str(issue) + '.json'
    )
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text('{"phase": "handoff"}')
    return None
  if (root / '.simulate-mismatch').exists():
    return {**evidence, "manualCase": "issue-702-manual--foreign"}
  return evidence
'''


class TestManualLauncher(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    base = Path(self.temp.name)
    self.engine = base / "engine"
    self.engine.mkdir()
    shutil.copy2(SOURCE / "repo_workflow.py", self.engine)
    shutil.copy2(SOURCE / "rwf", self.engine)
    shutil.copytree(SOURCE / "scripts", self.engine / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(SOURCE / "repo_workflow", self.engine / "repo_workflow",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (self.engine / "repo_workflow" / "manual_test_catalogue.py").write_text(
      CATALOGUE_STUB
    )
    (self.engine / "repo_workflow" / "manual_test_result.py").write_text(
      RESULT_STUB
    )
    (self.engine / "repo_workflow" / "manual_test_state.py").write_text(
      RESULT_STUB
    )
    self.root = base / "consumer"
    self.root.mkdir()
    self.git("init", "-b", "issue-702-test")
    self.git("config", "user.name", "Fixture")
    self.git("config", "user.email", "fixture@example.invalid")
    (self.root / "README").write_text("candidate")
    self.git("add", "README")
    self.git("commit", "-m", "candidate")
    self.sha = self.git("rev-parse", "HEAD")
    self.cases = [
      {
        "name": "issue-702-manual--z-last",
        "instructions": "Check final workflow",
        "expected_result": "Last step passes",
        "definition_digest": "z" * 64,
      },
      {
        "name": "issue-702-manual--a-first",
        "instructions": "Check initial workflow",
        "expected_result": "First step passes",
        "definition_digest": "a" * 64,
      },
    ]
    (self.root / ".manual-cases.json").write_text(json.dumps(self.cases))

  def tearDown(self):
    self.temp.cleanup()

  def git(self, *args):
    return subprocess.run(
      ["git", "-C", str(self.root), *args],
      check=True, text=True, capture_output=True,
    ).stdout.strip()

  def cli(self, *args):
    return subprocess.run(
      [sys.executable, str(self.engine / "repo_workflow.py"),
       "--root", str(self.root), *args],
      check=False, text=True, capture_output=True,
    )

  def test_launcher_help_and_completion(self):
    root = self.cli("test", "--help")
    self.assertEqual(root.returncode, 0, root.stderr)
    for name in ("RED", "temporary", "GREEN", "regression",
                 "integration", "results"):
      self.assertIn(name, root.stdout)
    detail = self.cli("test", "integration", "--help")
    self.assertEqual(detail.returncode, 0, detail.stderr)
    self.assertIn("--manual", detail.stdout)
    self.assertIn("--remote", detail.stdout)
    detailed = self.cli("complete", "--describe", "test", "integration", "")
    self.assertEqual(detailed.returncode, 0, detailed.stderr)
    self.assertIn("issue-702-manual--a-first", detailed.stdout)
    self.assertIn("issue-702-manual--z-last", detailed.stdout)
    self.assertIn("Select manual integration test", detailed.stdout)
    absent = self.cli("complete", "test", "")
    self.assertNotIn("succeeded", absent.stdout)
    self.assertNotIn("failed", absent.stdout)

  def test_first_outstanding_explicit_and_sequential_pass(self):
    first = self.cli("test", "integration", "--manual")
    self.assertEqual(first.returncode, 0, first.stderr)
    self.assertIn("issue-702-manual--a-first", first.stdout)
    self.assertIn("Check initial workflow", first.stdout)
    self.assertIn("First step passes", first.stdout)
    active = self.cli("complete", "test", "")
    self.assertIn("succeeded", active.stdout)
    self.assertIn("failed", active.stdout)
    active_names = self.cli("complete", "test", "integration", "")
    self.assertIn("issue-702-manual--a-first", active_names.stdout)
    self.assertNotIn("issue-702-manual--z-last", active_names.stdout)
    resumed = self.cli("test", "integration", "issue-702-manual--a-first")
    self.assertEqual(resumed.returncode, 0, resumed.stderr)
    self.assertIn("a-first", resumed.stdout)
    passed = self.cli("test", "succeeded")
    self.assertEqual(passed.returncode, 0, passed.stderr)
    self.assertIn("a-first", passed.stdout)
    outstanding_names = self.cli("complete", "test", "integration", "")
    self.assertIn("issue-702-manual--z-last", outstanding_names.stdout)
    self.assertNotIn("issue-702-manual--a-first", outstanding_names.stdout)
    explicit_terminal = self.cli(
      "test", "integration", "issue-702-manual--a-first"
    )
    self.assertEqual(explicit_terminal.returncode, 2)
    self.assertIn("terminal result", explicit_terminal.stderr)
    duplicate = self.cli("test", "succeeded")
    self.assertEqual(duplicate.returncode, 2)
    self.assertIn("exactly one active", duplicate.stderr)
    next_case = self.cli("test", "integration", "--manual")
    self.assertEqual(next_case.returncode, 0, next_case.stderr)
    self.assertIn("z-last", next_case.stdout)
    self.assertNotIn("a-first", next_case.stdout)
    passed_last = self.cli("test", "succeeded")
    self.assertEqual(passed_last.returncode, 0, passed_last.stderr)
    exhausted = self.cli("test", "integration", "--manual")
    self.assertEqual(exhausted.returncode, 0, exhausted.stderr)
    self.assertIn("No outstanding", exhausted.stdout)
    entries = self.cli("test", "results")
    self.assertEqual(entries.returncode, 0, entries.stderr)
    records = [json.loads(x) for x in entries.stdout.splitlines()]
    self.assertEqual(len(records), 2)
    self.assertEqual([x["manualCase"] for x in records],
                     ["issue-702-manual--a-first",
                      "issue-702-manual--z-last"])

  def test_pending_manual_result_must_not_complete_gate(self):
    self.assertEqual(self.cli("test", "integration", "--manual").returncode, 0)
    pending = self.root / ".repoworkflow" / "manual" / "pending-702.json"
    pending.parent.mkdir(parents=True)
    pending.write_text('{"phase":"handoff"}')
    response = self.cli("test", "succeeded")
    self.assertEqual(response.returncode, 2)
    self.assertIn("UNKNOWN", response.stderr)
    self.assertFalse((self.root / ".manual-results.json").exists())

  def test_terminal_evidence_hides_result_transition_even_if_selection_lingers(self):
    selected = self.cli("test", "integration", "--manual")
    self.assertEqual(selected.returncode, 0, selected.stderr)
    before = self.cli("complete", "test", "")
    self.assertIn("succeeded", before.stdout)
    self.assertIn("failed", before.stdout)
    case = "issue-702-manual--a-first"
    path = self.root / ".manual-results.json"
    saved = {self.sha: {case: "succeeded"}}
    path.write_text(json.dumps(saved))
    after = self.cli("complete", "test", "")
    self.assertEqual(after.returncode, 0, after.stderr)
    self.assertNotIn("succeeded", after.stdout)
    self.assertNotIn("failed", after.stdout)
    outcome = self.cli("test", "succeeded")
    self.assertEqual(outcome.returncode, 2)
    self.assertIn("terminal result", outcome.stderr)
    self.assertEqual(json.loads(path.read_text()), saved)
    self.assertTrue((self.root / ".manual-active.json").exists())

  def test_failed_case_blocks_same_candidate_and_retains_evidence(self):
    selected = self.cli("test", "integration", "issue-702-manual--z-last")
    self.assertEqual(selected.returncode, 0, selected.stderr)
    failed = self.cli("test", "failed")
    self.assertEqual(failed.returncode, 1, failed.stderr)
    self.assertIn("FAILED", failed.stdout)
    retry = self.cli("test", "integration", "--manual")
    self.assertEqual(retry.returncode, 2)
    self.assertIn("repair required", retry.stderr)
    legal_names = self.cli("complete", "test", "integration", "")
    self.assertNotIn("issue-702-manual--a-first", legal_names.stdout)
    self.assertNotIn("issue-702-manual--z-last", legal_names.stdout)
    recorded = self.cli("test", "results")
    self.assertEqual(recorded.returncode, 0, recorded.stderr)
    evidence = json.loads(recorded.stdout)
    self.assertEqual(evidence["result"], "failed")
    self.assertEqual(evidence["testSHA"], self.sha)

  def test_shipped_fail_confirmed_after_durable_q_increment_r_zero(self):
    (self.root / ".simulate-fail-version").write_text("1")
    (self.root / "VERSION").write_text("1.2.2-issue.702.3" + chr(10))
    self.assertEqual(self.cli("test", "integration", "--manual").returncode, 0)
    observed = self.cli("test", "failed")
    self.assertEqual(observed.returncode, 1, observed.stderr)
    self.assertIn("Manual integration FAILED:", observed.stdout)
    self.assertEqual((self.root / "VERSION").read_text().strip(),
                     "1.2.3-issue.702.0")
    self.assertTrue((self.root / ".version-bumped-by-fail").exists())
    log = self.root / ".repoworkflow/validation/testResults-702.jsonl"
    records = [json.loads(line) for line in log.read_text().splitlines()]
    self.assertEqual(len(records), 1)
    self.assertEqual(records[0]["result"], "failed")
    self.assertEqual(records[0]["testSHA"], self.sha)
    retry = self.cli("test", "failed")
    self.assertNotEqual(retry.returncode, 0)
    self.assertEqual(len(log.read_text().splitlines()), 1)

  def test_shipped_fail_unknown_receipt_never_claims_success(self):
    (self.root / ".simulate-unknown").write_text("1")
    self.assertEqual(self.cli("test", "integration", "--manual").returncode, 0)
    observed = self.cli("test", "failed")
    self.assertEqual(observed.returncode, 2)
    self.assertIn("UNKNOWN", observed.stderr)
    self.assertNotIn("Manual integration FAILED:", observed.stdout)
    log = self.root / ".repoworkflow/validation/testResults-702.jsonl"
    self.assertEqual(len(log.read_text().splitlines()), 1)
    self.assertNotEqual(self.cli("test", "failed").returncode, 0)
    self.assertEqual(len(log.read_text().splitlines()), 1)

  def test_postwrite_foreign_ack_fails_closed_without_replay(self):
    (self.root / ".simulate-mismatch").write_text("1")
    self.assertEqual(self.cli("test", "integration", "--manual").returncode, 0)
    receipt = self.cli("test", "succeeded")
    self.assertEqual(receipt.returncode, 2)
    self.assertIn("UNKNOWN", receipt.stderr)
    self.assertNotIn("Manual integration SUCCEEDED", receipt.stdout)
    log = self.root / ".repoworkflow/validation/testResults-702.jsonl"
    self.assertEqual(len(log.read_text().splitlines()), 1)
    self.assertNotEqual(self.cli("test", "succeeded").returncode, 0)
    self.assertEqual(len(log.read_text().splitlines()), 1)

  def test_empty_invalid_remote_and_result_without_selection(self):
    for cmd in (("test", "succeeded"), ("test", "failed")):
      with self.subTest(cmd=cmd):
        result = self.cli(*cmd)
        self.assertEqual(result.returncode, 2)
        self.assertIn("exactly one active", result.stderr)
    for args in (
      ("test", "integration", "--manual", "--remote"),
      ("test", "integration", "issue-702-manual--a-first", "--remote"),
      ("test", "integration", "--manual", "issue-702-manual--a-first"),
      ("test", "integration", "issue-702-manual--not-registered"),
    ):
      with self.subTest(args=args):
        result = self.cli(*args)
        self.assertNotEqual(result.returncode, 0)
        if "--remote" in args:
          self.assertIn("manual integration cannot use --remote", result.stderr)
    self.assertFalse((self.root / ".ci/run").exists())
    self.assertFalse((self.root / ".manual-active.json").exists())
    (self.root / ".manual-cases.json").write_text("[]")
    empty = self.cli("test", "integration", "--manual")
    self.assertEqual(empty.returncode, 0, empty.stderr)
    self.assertIn("No manual tests required", empty.stdout)

  def test_stale_multiple_and_definition_drift_fail_closed(self):
    self.assertEqual(self.cli("test", "integration", "--manual").returncode, 0)
    path = self.root / ".manual-active.json"
    original = json.loads(path.read_text())
    path.write_text(json.dumps([original, original]))
    ambiguous = self.cli("test", "succeeded")
    self.assertEqual(ambiguous.returncode, 2)
    self.assertIn("multiple active", ambiguous.stderr)
    path.write_text(json.dumps(original))
    drift = self.cases.copy()
    drift[1] = {**drift[1], "definition_digest": "b" * 64}
    (self.root / ".manual-cases.json").write_text(json.dumps(drift))
    stale = self.cli("test", "succeeded")
    self.assertEqual(stale.returncode, 2)
    self.assertIn("stale", stale.stderr)
    (self.root / ".manual-cases.json").write_text(json.dumps(self.cases))
    self.git("commit", "--allow-empty", "-m", "new candidate")
    sha_drift = self.cli("test", "failed")
    self.assertEqual(sha_drift.returncode, 2)
    self.assertIn("exactly one active", sha_drift.stderr)
    self.assertFalse((self.root / ".manual-results.json").exists())

  def test_existing_help_and_invalid_public_commands(self):
    self.assertNotEqual(self.cli("validate", "integration").returncode, 0)
    self.assertEqual(self.cli("test", "results", "--help").returncode, 0)
    self.assertNotEqual(self.cli("test", "succeeded", "--remote").returncode, 0)
    self.assertNotEqual(self.cli("test", "failed", "extra").returncode, 0)


class TestAutomaticIntegrationPresentation(unittest.TestCase):
  def test_shipped_help_outside_git_checkout(self):
    with tempfile.TemporaryDirectory() as temp:
      proc = subprocess.run(
        [sys.executable, str(SOURCE / "repo_workflow.py"),
         "--root", temp, "test", "--help"],
        capture_output=True, text=True, check=False,
      )
      self.assertEqual(proc.returncode, 0, proc.stderr)
      self.assertIn("integration", proc.stdout)
      self.assertNotIn("succeeded", proc.stdout)
      self.assertNotIn("failed", proc.stdout)

  def test_terminal_publication_is_blocked_until_mit_finishes(self):
    from repo_workflow.test_cli import run_test
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp) / "work"
      root.mkdir()
      engine = Path(temp) / "other-engine"
      engine.mkdir()
      with patch("repo_workflow.test_cli.current_branch",
                 return_value="issue-702-fixture"):
        with patch("repo_workflow.test_cli.run_local_integration",
                   return_value=0):
          with patch("repo_workflow.test_cli.after_automatic_integration",
                     return_value=2):
            with patch("repo_workflow.test_cli.publish_local_terminal") as pub:
              self.assertEqual(run_test(
                root, "integration", remote=False, engine_root=engine
              ), 2)
              pub.assert_not_called()
          with patch("repo_workflow.test_cli.after_automatic_integration",
                     return_value=0):
            with patch("repo_workflow.test_cli.publish_local_terminal") as pub:
              self.assertEqual(run_test(
                root, "integration", remote=False, engine_root=engine
              ), 0)
              pub.assert_called_once_with(root, stage="integration")

  def test_legacy_nonmanual_catalogue_does_not_require_new_engine(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      (root / ".ci").mkdir()
      (root / ".ci" / "tests.json").write_text('{"tests": []}')
      self.assertEqual(after_automatic_integration(root), 0)

  def test_escaped_manual_name_reaches_authoritative_a_gate(self):
    from types import ModuleType, SimpleNamespace
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      (root / ".ci").mkdir()
      (root / ".ci" / "tests.json").write_text(
        '{"tests": [{"issue-702-manual\\u002d\\u002dfirst": '
        '{"type": "manual"}}]}'
      )
      module = ModuleType("repo_workflow.manual_test_catalogue")
      module.read_manual_cases = lambda root, issue: ()
      case = SimpleNamespace(name="issue-702-manual--first")
      with patch.dict(sys.modules, {
        "repo_workflow.manual_test_catalogue": module
      }):
        with patch("repo_workflow.manual_test_cli._outstanding",
                   return_value=(702, "a" * 40, (case,), {}, object())) as gate:
          self.assertEqual(after_automatic_integration(root), 2)
          gate.assert_called_once_with(root)

  def test_manual_marker_never_silently_passes_without_adapter(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      (root / ".ci").mkdir()
      (root / ".ci" / "tests.json").write_text(
        '{"tests": [{"issue-702-manual--first": {}}]}'
      )
      with patch.dict(sys.modules, {"repo_workflow.manual_test_catalogue": None}):
        with patch("repo_workflow.manual_test_cli._issue", return_value=702):
          with patch("repo_workflow.manual_test_cli.head_sha", return_value="a" * 40):
            with self.assertRaisesRegex(Exception, "catalogue"):
              after_automatic_integration(root)


if __name__ == "__main__":
  unittest.main()
