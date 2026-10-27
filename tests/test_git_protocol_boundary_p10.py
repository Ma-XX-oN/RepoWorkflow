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
    command(self.root, 'config', 'core.autocrlf', 'false')
    (self.root / 'tracked.txt').write_bytes(b'original\n')
    command(self.root, 'add', 'tracked.txt')
    command(self.root, 'commit', '-qm', 'baseline')

  def test_status_unicode_spaces_and_literal_backslash(self):
    with open(os.fsencode(self.root) + b'/spaces \xc3\xa9.txt', 'wb') as f:
      f.write(b'x')
    (self.root / 'tracked.txt').write_text('dirty')
    expected = ['spaces é.txt', 'tracked.txt']
    if os.name != 'nt':
      (self.root / 'a\\b.txt').write_text('slash')
      expected.append('a\\b.txt')
    self.assertEqual(changed_files(self.root), sorted(expected))

  def test_status_does_not_refresh_the_real_index(self):
    # A content-identical rewrite changes stat metadata; ordinary git status
    # updates the index cache even when porcelain output is unchanged.
    import time
    index = self.root / '.git' / 'index'
    before = index.read_bytes()
    time.sleep(1)
    (self.root / 'tracked.txt').write_bytes(b'original\n')
    self.assertEqual(changed_files(self.root), [])
    self.assertEqual(index.read_bytes(), before)

  def test_wire_bytes_and_unsafe_paths(self):
    self.assertEqual(git_wire_path('a é/x y'.encode()), 'a é/x y')
    self.assertEqual(git_native_path(b'a/b'), Path('a') / 'b')
    for raw in (b'../a', b'a/../b', b'/root', b'a//b', b'a/./b', b'', b'\xff'):
      with self.subTest(raw=raw), self.assertRaises(GitError):
        git_wire_path(raw)

  def test_git_unicode_argument_under_ascii_locale(self):
    with open(os.fsencode(self.root) + b'/\xc3\xa9.txt', 'wb') as f:
      f.write(b'unicode-argv\n')
    result = git(self.root, 'add', '--', 'é.txt')
    self.assertEqual(result.returncode, 0)
    self.assertEqual(result.args, ['git', 'add', '--', 'é.txt'])
    self.assertIn(b'\xc3\xa9.txt', git_bytes(self.root, 'ls-files', '-z').stdout)

  def test_git_native_path_arguments_roundtrip_under_ascii_locale(self):
    raw = 'é-native.txt'.encode('utf-8')
    with open(os.fsencode(self.root) + b'/' + raw, 'wb') as f:
      f.write(b'x')
    result = git(self.root, 'add', '--', str(git_native_path(raw)))
    self.assertEqual(result.returncode, 0)
    self.assertIn(raw, git_bytes(self.root, 'ls-files', '-z').stdout)

  def test_unicode_repository_root_under_ascii_locale(self):
    native = Path(os.fsdecode(os.fsencode(self.temp.name) + b'/\xc3\xa9-root'))
    native.mkdir()
    command(native, 'init', '-q')
    self.assertEqual(git(Path(self.temp.name) / 'é-root', 'rev-parse', '--is-inside-work-tree').stdout.strip(), 'true')

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

  def test_checkout_uses_committed_attributes_not_dirty_worktree(self):
    (self.root / '.gitattributes').write_text('tracked.txt text eol=crlf\n')
    command(self.root, 'add', '.gitattributes')
    command(self.root, 'commit', '-qm', 'attr-snapshot')
    (self.root / '.gitattributes').write_text('tracked.txt -text\n')
    before = command(self.root, 'status', '--porcelain', '-z').stdout
    self.assertEqual(git_checkout_bytes(self.root, 'tracked.txt'), b'original\r\n')
    self.assertEqual(command(self.root, 'status', '--porcelain', '-z').stdout, before)

  def test_materializer_smudge_filter(self):
    command(self.root, 'config', 'filter.p10.smudge', 'tr a-z A-Z')
    command(self.root, 'config', 'filter.p10.clean', 'cat')
    (self.root / '.gitattributes').write_text('tracked.txt filter=p10\n')
    command(self.root, 'add', '.gitattributes')
    command(self.root, 'commit', '-qm', 'filter')
    self.assertEqual(git_checkout_bytes(self.root, 'tracked.txt'), b'ORIGINAL\n')

  def test_unicode_committed_checkout_under_host_locale(self):
    with open(os.fsencode(self.root) + b'/\xc3\xa9.txt', 'wb') as f:
      f.write(b'unicode-name\n')
    command(self.root, 'add', '.')
    command(self.root, 'commit', '-qm', 'unicode')
    self.assertEqual(git_checkout_bytes(self.root, 'é.txt'), b'unicode-name\n')
    self.assertEqual(git_checkout_bytes(self.root, git_native_path('é.txt'.encode())), b'unicode-name\n')

  def test_exact_treeish_not_current_worktree(self):
    previous = command(self.root, 'rev-parse', 'HEAD').stdout.decode('ascii').strip()
    (self.root / 'tracked.txt').write_bytes(b'next\n')
    command(self.root, 'add', 'tracked.txt')
    command(self.root, 'commit', '-qm', 'next')
    self.assertEqual(git_checkout_bytes(self.root, 'tracked.txt'), b'next\n')
    self.assertEqual(git_checkout_bytes(self.root, 'tracked.txt', treeish=previous), b'original\n')

  def test_unicode_treeish_under_ascii_locale(self):
    git(self.root, 'branch', 'éref')
    self.assertEqual(git_checkout_bytes(self.root, 'tracked.txt', treeish='éref'), b'original\n')

  def test_checkout_pathspec_is_literal(self):
    self.assertIsNone(git_checkout_bytes(self.root, '*.txt'))
    self.assertIsNone(git_checkout_bytes(self.root, 'track'))

  def test_committed_literal_backslash_checkout(self):
    if os.name == 'nt':
      # No native filename can contain a literal backslash on Windows.
      with self.assertRaisesRegex(GitError, 'native path'):
        git_checkout_bytes(self.root, 'file\\name.txt')
      return
    (self.root / 'file\\name.txt').write_bytes(b'literal\n')
    command(self.root, 'add', '--', 'file\\name.txt')
    command(self.root, 'commit', '-qm', 'backslash')
    self.assertEqual(git_checkout_bytes(self.root, 'file\\name.txt'), b'literal\n')

  def test_executable_git_mode_materializes_regular_file(self):
    # Git index mode is authoritative even where core.filemode is false.
    command(self.root, 'update-index', '--chmod=+x', 'tracked.txt')
    command(self.root, 'commit', '-qm', 'executable')
    self.assertTrue(command(self.root, 'ls-files', '--stage', '--', 'tracked.txt').stdout.startswith(b'100755 '))
    self.assertEqual(git_checkout_bytes(self.root, 'tracked.txt'), b'original\n')

  def test_autocrlf_checkout_uses_git_configuration(self):
    command(self.root, 'config', 'core.autocrlf', 'true')
    self.assertEqual(git_checkout_bytes(self.root, 'tracked.txt'), b'original\r\n')

  def test_invalid_git_protocol_is_controlled(self):
    fake = subprocess.CompletedProcess(['git'], 0, b'\xff', b'')
    with patch('repo_workflow.git.git_bytes', return_value=fake):
      with self.assertRaisesRegex(GitError, 'invalid UTF-8'):
        git(self.root, 'anything')

  def test_git_check_true_rejects_invalid_utf8_diagnostic(self):
    fake = subprocess.CompletedProcess(['git'], 1, b'', b'\xff')
    with patch('repo_workflow.git.subprocess.run', return_value=fake):
      with self.assertRaisesRegex(GitError, 'invalid UTF-8'):
        git_bytes(self.root, 'anything')

  def test_git_oserror_wrapped(self):
    with patch('repo_workflow.git.subprocess.run', side_effect=OSError('not executable')):
      with self.assertRaisesRegex(GitError, 'cannot execute git'):
        git_bytes(self.root, 'status')

  def test_git_check_false_retains_nonzero_and_raw_diagnostics(self):
    sample = subprocess.CompletedProcess(['git'], 4, b'out\xff', b'error\xff')
    with patch('repo_workflow.git.subprocess.run', return_value=sample):
      result = git_bytes(self.root, 'push', check=False)
      self.assertEqual((result.returncode, result.stdout, result.stderr), (4, b'out\xff', b'error\xff'))
      with self.assertRaises(GitError):
        git_bytes(self.root, 'push')

  def test_injected_malformed_status_records(self):
    for wire in (b'?? ../escape\0', b'?? bad\xff\0', b'R  dest\0', b'?? a', b'?? a\0?? /root\0'):
      with self.subTest(wire=wire):
        with patch('repo_workflow.git.git_bytes', return_value=subprocess.CompletedProcess(['git'], 0, wire, b'')):
          with self.assertRaises(GitError):
            changed_files(self.root)

  def test_injected_raw_nul_status_unicode_and_rename_on_every_os(self):
    # Protocol semantics need no host filesystem capability for these names.
    wire = b'?? space \xc3\xa9.txt\0R  line\nname.txt\0old.txt\0?? brackets[1]*?.txt\0'
    fake = subprocess.CompletedProcess(['git'], 0, wire, b'')
    with patch('repo_workflow.git.git_bytes', return_value=fake):
      self.assertEqual(changed_files(self.root), ['brackets[1]*?.txt', 'line\nname.txt', 'space é.txt'])

  def test_backslash_wire_path_uses_native_capability_boundary(self):
    raw = b'literal\\backslash.txt'
    if os.name == 'nt':
      # Windows cannot store this as a single native path segment.
      with self.assertRaisesRegex(GitError, 'native path'):
        git_wire_path(raw)
    else:
      self.assertEqual(git_wire_path(raw), 'literal\\backslash.txt')

  def test_rename_reports_destination_not_source(self):
    command(self.root, 'mv', 'tracked.txt', 'new name.txt')
    self.assertEqual(changed_files(self.root), ['new name.txt'])

  def test_checkout_refuses_to_follow_committed_symlink(self):
    # Commit a symlink using Git's portable index API, not host symlink privileges.
    blob = subprocess.run(['git', 'hash-object', '-w', '--stdin'], cwd=self.root, input=b'tracked.txt', capture_output=True, check=True).stdout.decode('ascii').strip()
    command(self.root, 'update-index', '--add', '--cacheinfo', '120000,' + blob + ',linked')
    command(self.root, 'commit', '-qm', 'symlink')
    with self.assertRaisesRegex(GitError, 'symbolic link'):
      git_checkout_bytes(self.root, 'linked')

  def test_committed_symlink_rejected_with_core_symlinks_false(self):
    blob = subprocess.run(['git', 'hash-object', '-w', '--stdin'], cwd=self.root, input=b'tracked.txt', capture_output=True, check=True).stdout.decode('ascii').strip()
    command(self.root, 'update-index', '--add', '--cacheinfo', '120000,' + blob + ',linked')
    command(self.root, 'commit', '-qm', 'symlink')
    command(self.root, 'config', 'core.symlinks', 'false')
    with self.assertRaisesRegex(GitError, 'regular Git file'):
      git_checkout_bytes(self.root, 'linked')

  def test_checkout_rejects_traversal(self):
    with self.assertRaises(GitError):
      git_checkout_bytes(self.root, '../tracked.txt')


if __name__ == '__main__':
  unittest.main()
