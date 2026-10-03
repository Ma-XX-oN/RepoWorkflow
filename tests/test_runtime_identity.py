from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from repo_workflow.runtime_identity import (
  RuntimeIdentityError,
  runtime_writer_identity,
)


class RuntimeIdentityTests(unittest.TestCase):
  def test_reads_exact_environment_inputs(self):
    identity = runtime_writer_identity({
      "RWF_WRITER_ID": "agent:alpha",
      "RWF_SESSION_ID": "session:17",
      "USER": "ignored",
    })
    self.assertEqual(identity.writer_id, "agent:alpha")
    self.assertEqual(identity.session_id, "session:17")

  def test_missing_writer_fails_closed(self):
    with self.assertRaisesRegex(
      RuntimeIdentityError,
      "RWF_WRITER_ID",
    ):
      runtime_writer_identity({"RWF_SESSION_ID": "session:17"})

  def test_missing_session_fails_closed(self):
    with self.assertRaisesRegex(
      RuntimeIdentityError,
      "RWF_SESSION_ID",
    ):
      runtime_writer_identity({"RWF_WRITER_ID": "agent:alpha"})

  def test_malformed_identity_uses_canonical_validation(self):
    with self.assertRaisesRegex(
      RuntimeIdentityError,
      "writer_id must be non-empty text without whitespace",
    ):
      runtime_writer_identity({
        "RWF_WRITER_ID": "not valid",
        "RWF_SESSION_ID": "session:17",
      })

  def test_does_not_infer_identity_from_other_process_inputs(self):
    with self.assertRaises(RuntimeIdentityError):
      runtime_writer_identity({
        "USER": "agent-alpha",
        "PID": "123",
        "GITHUB_ACTOR": "agent-alpha",
      })

  def test_default_source_is_process_environment(self):
    with patch.dict(
      os.environ,
      {
        "RWF_WRITER_ID": "agent:alpha",
        "RWF_SESSION_ID": "session:17",
      },
      clear=True,
    ):
      identity = runtime_writer_identity()
    self.assertEqual(identity.writer_id, "agent:alpha")
    self.assertEqual(identity.session_id, "session:17")


if __name__ == "__main__":
  unittest.main()
