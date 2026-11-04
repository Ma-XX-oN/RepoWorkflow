"""P16: physical LF-delimited JSONL terminal observation regression tests."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.local_terminal import publish_local_terminal
from repo_workflow.terminal_tag import TerminalTagError


class PhysicalJsonlTerminalTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    self.log = self.root / ".repoworkflow/validation/testResults-572.jsonl"
    self.log.parent.mkdir(parents=True)
    branch = patch("repo_workflow.local_terminal.current_branch",
                   return_value="issue-572-cert")
    publisher = patch("repo_workflow.local_terminal.publish_terminal_tag",
                      return_value="published")
    branch.start()
    self.publish = publisher.start()
    self.addCleanup(branch.stop)
    self.addCleanup(publisher.stop)

  def observation(self, **changes):
    record = {
      "kind": "regression", "result": "succeeded",
      "testSHA": "c" * 40, "testVersion": "0.1.122-issue.572.0.1",
      "headChangedDuringTest": False, "uncommittedChanges": [],
      "runner": "local",
    }
    record.update(changes)
    return record

  def write_records(self, *records, final_lf=True):
    text = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    self.log.write_text(text + ("\n" if final_lf else ""), encoding="utf-8")

  def publish_success(self):
    self.assertEqual(publish_local_terminal(self.root, stage="regression"),
                     "published")
    self.publish.assert_called_once()
    kwargs = self.publish.call_args.kwargs
    self.assertEqual(kwargs["candidate"], "c" * 40)
    self.assertEqual(kwargs["version"], "0.1.122-issue.572.0.1")
    self.assertEqual(kwargs["outcome"], "PASS")
    self.assertEqual(kwargs["stage"], "regression")
    self.assertEqual(kwargs["canonical_log"], self.log)

  def test_u2028_inside_latest_valid_json_string_is_not_a_record_boundary(self):
    self.write_records(self.observation(message="before\u2028after"))
    self.publish_success()

  def test_u2029_inside_latest_valid_unicode_status_metadata(self):
    self.write_records(self.observation(statusMetadata="x\u2029y"))
    self.publish_success()

  def test_last_physical_record_selected_without_unicode_line_splitting(self):
    self.write_records(self.observation(result="failed"),
                       self.observation(message="alpha\u2028beta\u2029gamma"))
    self.publish_success()

  def test_terminal_record_crlf_is_accepted(self):
    text = json.dumps(self.observation(message="a\u2028b"),
                      ensure_ascii=False) + "\r\n"
    self.log.write_bytes(text.encode("utf-8"))
    self.publish_success()

  def test_single_unterminated_complete_json_record_remains_supported(self):
    self.write_records(self.observation(), final_lf=False)
    self.publish_success()

  def assert_unavailable(self):
    with self.assertRaisesRegex(TerminalTagError, "unavailable"):
      publish_local_terminal(self.root, stage="regression")
    self.publish.assert_not_called()

  def test_missing_and_empty_log_fail_closed(self):
    self.assert_unavailable()
    self.log.write_bytes(b"")
    self.assert_unavailable()

  def test_invalid_utf8_fails_closed(self):
    self.log.write_bytes(b'{"kind":"regression","message":"\xff"}\n')
    self.assert_unavailable()

  def test_truncated_last_record_does_not_fall_back_to_previous_success(self):
    self.write_records(self.observation())
    with self.log.open("ab") as stream:
      stream.write(b'{"kind":"regression","result":')
    self.assert_unavailable()

  def test_blank_last_record_does_not_fall_back(self):
    self.write_records(self.observation())
    with self.log.open("ab") as stream:
      stream.write(b"\n")
    self.assert_unavailable()

  def test_malformed_last_record_does_not_fall_back(self):
    self.write_records(self.observation())
    with self.log.open("ab") as stream:
      stream.write(b"{bad json\n")
    self.assert_unavailable()

  def test_directory_in_place_of_log_fails_closed(self):
    self.log.mkdir()
    self.assert_unavailable()

  def test_wrong_stage_refused_and_incomplete_does_not_publish(self):
    self.write_records(self.observation(kind="integration"))
    with self.assertRaisesRegex(TerminalTagError, "not the terminal stage"):
      publish_local_terminal(self.root, stage="regression")
    self.write_records(self.observation(result="incomplete"))
    self.assertIsNone(publish_local_terminal(self.root, stage="regression"))
    self.publish.assert_not_called()

  def test_failed_terminal_record_keeps_failure_outcome(self):
    self.write_records(self.observation(result="failed"))
    self.assertEqual(publish_local_terminal(self.root, stage="regression"),
                     "published")
    self.assertEqual(self.publish.call_args.kwargs["outcome"], "FAIL")

  def test_nonreusable_and_invalid_outcome_do_not_publish(self):
    for record in (
      self.observation(headChangedDuringTest=True),
      self.observation(uncommittedChanges=["changed"]),
    ):
      self.write_records(record)
      self.assertIsNone(publish_local_terminal(self.root, stage="regression"))
    self.write_records(self.observation(result="unexpected"))
    with self.assertRaisesRegex(TerminalTagError, "not definitive"):
      publish_local_terminal(self.root, stage="regression")
    self.publish.assert_not_called()


if __name__ == "__main__":
  unittest.main()
