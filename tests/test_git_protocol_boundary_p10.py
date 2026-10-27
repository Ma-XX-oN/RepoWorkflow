import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from repo_workflow.git import GitError, git, git_bytes, changed_files, git_checkout_bytes, git_native_path, git_wire_path


def command(root, *args):
  return subprocess.run(['git', *args], cwd=root, capture_output=True, check=True)


class GitProtocolBoundaryP10(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    command(self.root, 'init', '-q')
    command(self.root, 'config', 'user.email', 'p10@example.test')
    command(self.root, 'config', 'user.name', 'P10 Test')
    (self.root / 'tracked.txt').write_bytes(b'original\n')
    command(self.root, 'add', 'tracked.txt')
    command(self.root, 'commit', '-qm', 'baseline')

  def test_status_unicode_spaces_and_literal_backslash(self):
    (self.root / 'spaces é.txt').write_text('x')
    (self.root / 'tracked.txt').write_text('dirty')
    expected = ['spaces é.txt', 'tracked.txt']
    if os.name != 'nt':
      (self.root / 'a\\b.txt').write_text('slash')
      expected.append('a\\b.txt')
    self.assertEqual(changed_files(self.root), sorted(expected))

  def test_wire_bytes_and_unsafe_paths(self):
    self.assertEqual(git_wire_path('a é/x y'.encode()), 'a é/x y')
    self.assertEqual(git_native_path(b'a/b'), Path('a') / 'b')
    for raw in (b'../a', b'a/../b', b'/root', b'a//b', b'a/./b', b'', b'\xff'):
      with self.subTest(raw=raw), self.assertRaises(GitError):
        git_wire_path(raw)

  def test_git_bytes_nonzero_and_strict_text(self):
    missing = git_bytes(self.root, 'rev-parse', '--verify', 'not-a-ref', check=False)
    self.assertNotEqual(missing.returncode, 0)
    self.assertIsInstance(missing.stderr, bytes)
    self.assertEqual(git(self.root, 'rev-parse', 'HEAD').returncode, 0)
    with self.assertRaises(GitError):
      git(self.root, 'rev-parse', '--verify', 'not-a-ref')

  def test_materializer_crlf_and_no_mutation(self):
    (self.root / '.gitattributes').write_text('tracked.txt text eol=crlf\n')
    command(self.root, 'add', '.gitattributes', 'tracked.txt')
    command(self.root, 'commit', '-qm', 'attributes')
    (self.root / 'tracked.txt').write_bytes(b'dirty\n')
    before_index = command(self.root, 'write-tree').stdout
    before_status = git_bytes(self.root, 'status', '--porcelain', '-z').stdout
    self.assertEqual(git_checkout_bytes(self.root, 'tracked.txt'), b'original\r\n')
    self.assertEqual((self.root / 'tracked.txt').read_bytes(), b'dirty\n')
    self.assertEqual(command(self.root, 'write-tree').stdout, before_index)
    self.assertEqual(git_bytes(self.root, 'status', '--porcelain', '-z').stdout, before_status)
    self.assertIsNone(git_checkout_bytes(self.root, 'absent.txt'))

  def test_materializer_smudge_filter(self):
    command(self.root, 'config', 'filter.p10.smudge', 'tr a-z A-Z')
    command(self.root, 'config', 'filter.p10.clean', 'cat')
    (self.root / '.gitattributes').write_text('tracked.txt filter=p10\n')
    command(self.root, 'add', '.gitattributes')
    command(self.root, 'commit', '-qm', 'filter')
    self.assertEqual(git_checkout_bytes(self.root, 'tracked.txt'), b'ORIGINAL\n')

  def test_checkout_rejects_traversal(self):
    with self.assertRaises(GitError):
      git_checkout_bytes(self.root, '../tracked.txt')


if __name__ == '__main__':
  unittest.main()
