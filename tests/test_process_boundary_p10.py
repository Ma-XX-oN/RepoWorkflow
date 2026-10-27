import os
from pathlib import Path
import sys
import tempfile
import unittest
from repo_workflow.process import run_command, run_command_bytes


class ProcessBoundaryP10(unittest.TestCase):
  def test_bytes_argv_cwd_env_stdin_stderr_exit(self):
    with tempfile.TemporaryDirectory() as td:
      code = ('import os,sys; b=sys.stdin.buffer.read(); '
              'sys.stdout.buffer.write(os.fsencode(os.getcwd())+b"|"+os.fsencode(os.environ["P10_TEST"])+b"|"+b); '
              'sys.stderr.buffer.write(b"ERR"); sys.exit(7)')
      env = dict(os.environ, P10_TEST='value')
      result = run_command_bytes([sys.executable, '-c', code], Path(td), env=env, input_data=b'\x00\xff')
      self.assertEqual(result.returncode, 7)
      self.assertEqual(result.stdout, os.fsencode(str(Path(td).resolve()))+b'|value|\x00\xff')
      self.assertEqual(result.stderr, b'ERR')
      self.assertEqual(result.command[:2], [sys.executable, '-c'])

  def test_utf8_and_invalid_utf8_fail_controlled(self):
    with tempfile.TemporaryDirectory() as td:
      ok = run_command([sys.executable, '-c', 'import sys;sys.stdout.buffer.write("\\u2192\\xe9".encode("utf-8"))'], Path(td))
      self.assertEqual((ok.returncode, ok.stdout), (0, '→é'))
      bad = run_command([sys.executable, '-c', 'import sys;sys.stdout.buffer.write(b"\\xff")'], Path(td))
      self.assertEqual(bad.returncode, 2)
      self.assertIn('invalid UTF-8', bad.stderr)
      raw = run_command_bytes([sys.executable, '-c', 'import sys;sys.stdout.buffer.write(b"\\xff")'], Path(td))
      self.assertEqual(raw.stdout, b'\xff')

  def test_legacy_encoded_output_is_not_host_decoded(self):
    with tempfile.TemporaryDirectory() as td:
      result = run_command([sys.executable, '-c', 'import sys;sys.stdout.buffer.write(b"\\x96")'], Path(td))
      self.assertEqual(result.returncode, 2)
      self.assertIn('invalid UTF-8', result.stderr)

  def test_missing_executable_controlled(self):
    with tempfile.TemporaryDirectory() as td:
      result = run_command_bytes(['p10-command-certainly-missing'], Path(td))
      self.assertEqual(result.returncode, 2)
      self.assertIn(b'unable to execute', result.stderr)


if __name__ == '__main__':
  unittest.main()
