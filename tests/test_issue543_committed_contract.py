"""Regression acceptance for committed RED/GREEN selections and real Git requests."""
import json
import unittest
from tests import test_test_cli as fixture
from tests.test_issue543_marker_integrity import CommittedMarkerIntegrityTests


class CommittedSelectionContract(unittest.TestCase):
  setUp = fixture.TestCliContract.setUp
  tearDown = fixture.TestCliContract.tearDown
  cli = fixture.TestCliContract.cli
  git = fixture.TestCliContract.git
  _catalogue = fixture.TestCliContract._catalogue

  def two_groups(self):
    path = self.root / '.ci/tests.json'
    self._catalogue(path, issue_group='issue-545-A')
    value = json.loads(path.read_text())
    value['tests'][0]['issue-545-B'] = {
      'type': 'regression', 'name': 'smoke_case',
    }
    path.write_text(json.dumps(value))
    self.git('add', '.ci/tests.json', 'smoke_case.py')
    self.git('commit', '-m', 'register two groups')
    self.assertEqual(self.cli('test', 'RED', 'issue-545-A').returncode, 2)
    return self.root / '.ci/red-green.txt'

  def test_uncommitted_selected_group_is_rejected(self):
    selection = self.two_groups()
    selection.write_text('issue-545-B\n')
    result = self.cli('test', 'GREEN')
    self.assertEqual(result.returncode, 2, result.stderr)
    self.assertEqual(self.git('show', 'HEAD:.ci/red-green.txt'), 'issue-545-A')

  def test_deleted_committed_selection_is_rejected(self):
    selection = self.two_groups()
    selection.unlink()
    result = self.cli('test', 'GREEN')
    self.assertEqual(result.returncode, 2, result.stderr)
    self.assertNotIn('testing skipped', result.stdout)

  def test_declared_expected_red_is_success_with_red_status(self):
    path = self.root / '.ci/tests.json'
    self._catalogue(path, issue_group='issue-545-red')
    value = json.loads(path.read_text())
    value['tests'][0]['issue-545-red']['expected-red'] = {
      'exit-code': 1, 'output-contains': 'EXPECTED_RED_543',
    }
    path.write_text(json.dumps(value))
    (self.root / 'smoke_case.py').write_text(
      'import unittest\nclass Smoke(unittest.TestCase):\n'
      '  def test_red(self): self.fail("EXPECTED_RED_543")\n'
    )
    self.git('add', '.ci/tests.json', 'smoke_case.py')
    self.git('commit', '-m', 'declare expectation before running')
    result = self.cli('test', 'RED', 'issue-545-red')
    path = self.root / '.repoworkflow/validation/testResults-545.jsonl'
    record = json.loads(path.read_text().splitlines()[-1])
    self.assertEqual((result.returncode, record['result'], record['redStatus']),
                     (0, 'succeeded', 'RED'))
    self.assertEqual(record['groups'][0]['exit_code'], 1)
    self.assertFalse(record['reusable'])

  def test_mismatched_declared_red_does_not_pass(self):
    path = self.root / '.ci/tests.json'
    self._catalogue(path, issue_group='issue-545-red')
    value = json.loads(path.read_text())
    value['tests'][0]['issue-545-red']['expected-red'] = {
      'exit-code': 3, 'output-contains': 'NONMATCHING_543',
    }
    path.write_text(json.dumps(value))
    (self.root / 'smoke_case.py').write_text(
      'import unittest\nclass Smoke(unittest.TestCase):\n'
      '  def test_red(self): self.fail("ACTUAL_FAILURE_543")\n'
    )
    self.git('add', '.ci/tests.json', 'smoke_case.py')
    self.git('commit', '-m', 'declare nonmatching expectation')
    result = self.cli('test', 'RED', 'issue-545-red')
    record = json.loads((self.root / '.repoworkflow/validation/testResults-545.jsonl')
                        .read_text().splitlines()[-1])
    self.assertEqual(result.returncode, 2)
    self.assertEqual(record['redStatus'], 'FAIL')
    self.assertEqual(record['result'], 'failed')


if __name__ == '__main__':
  unittest.main()
