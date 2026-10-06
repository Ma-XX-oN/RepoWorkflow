from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scripts.validate as validate_script


class ValidateScriptTests(unittest.TestCase):
  def test_malformed_committed_ticket_state_blocks_validation(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      state = root / ".repoworkflow"
      state.mkdir()
      (state / "tickets.csv").write_text(
        (
          "issue,title,dependencies\n"
          "10,Valid,\n"
          "20,Missing third field\n"
        ),
        encoding="utf-8",
      )
      with (
        patch.object(validate_script, "ROOT", root),
        patch.object(validate_script, "run") as run,
      ):
        self.assertEqual(validate_script.main(), 1)
      run.assert_not_called()

  def test_explicit_empty_dependency_field_reaches_test_execution(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      state = root / ".repoworkflow"
      state.mkdir()
      (state / "tickets.csv").write_text(
        "issue,title,dependencies\n10,Valid,\n",
        encoding="utf-8",
      )
      with (
        patch.object(validate_script, "ROOT", root),
        patch.object(validate_script, "run", side_effect=(0, 0)) as run,
      ):
        self.assertEqual(validate_script.main(), 0)
      self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
  unittest.main()
