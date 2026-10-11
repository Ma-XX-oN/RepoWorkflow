"""Specification-derived provider lineage and tamper acceptance for #543."""
import base64
from copy import deepcopy
import unittest
from repo_workflow.github_evidence import verify_hosted_stage

REPO = 'Ma-XX-oN/RepoWorkflow'
BASE = 'https://api.github.com/repos/' + REPO
CANDIDATE = 'a' * 40
FIRST = 'b' * 40
PUBLISHED = 'c' * 40
RETRY = 'd' * 40


def encoded(value):
  return {'encoding': 'base64', 'content': base64.b64encode(value.encode()).decode()}


class VerifiedRetryLineageTests(unittest.TestCase):
  def setUp(self):
    self.record = {
      'providerRunId': 123,
      'providerInvocationSHA': RETRY,
      'providerCandidateSHA': CANDIDATE,
      'providerStage': 'GREEN-testing',
    }
    self.responses = {
      BASE + '/actions/runs/123': {
        'id': 123, 'conclusion': 'success', 'status': 'completed',
        'event': 'push', 'name': 'RepoWorkflow On-Demand CI (candidate)',
        'head_sha': RETRY,
      },
      BASE + '/git/commits/' + RETRY: {'parents': [{'sha': PUBLISHED}]},
      BASE + '/contents/.ci/run?ref=' + RETRY: encoded('GREEN-testing ' + PUBLISHED + '\n'),
      BASE + '/commits/' + PUBLISHED: {
        'parents': [{'sha': FIRST}],
        'files': [{'filename': '.repoworkflow/validation/testResults-543.jsonl'}],
        'commit': {'message': 'test: publish hosted evidence from run 122'},
      },
      BASE + '/commits/' + FIRST: {
        'parents': [{'sha': CANDIDATE}],
        'files': [{'filename': '.ci/run'}],
        'commit': {'message': 'test: request GREEN'},
      },
      BASE + '/contents/.ci/run?ref=' + FIRST: encoded('GREEN-testing ' + CANDIDATE + '\n'),
      BASE + '/actions/runs/123/jobs?per_page=100': {
        'total_count': 2,
        'jobs': [{'name': 'plan', 'conclusion': 'success'},
                 {'name': 'validate', 'conclusion': 'success'}],
      },
    }

  def verify(self, responses=None):
    source = responses if responses is not None else self.responses
    return verify_hosted_stage(self.record, repo=REPO, stage='GREEN-testing',
                               read=lambda url: source[url])

  def test_valid_retry_after_publication_is_accepted(self):
    self.assertTrue(self.verify())

  def test_source_change_in_lineage_is_rejected(self):
    responses = deepcopy(self.responses)
    responses[BASE + '/commits/' + PUBLISHED]['files'][0]['filename'] = 'source.py'
    self.assertFalse(self.verify(responses))

  def test_unverified_publish_message_is_rejected(self):
    responses = deepcopy(self.responses)
    responses[BASE + '/commits/' + PUBLISHED]['commit']['message'] = 'normal source edit'
    self.assertFalse(self.verify(responses))

  def test_changed_intermediate_marker_is_rejected(self):
    responses = deepcopy(self.responses)
    responses[BASE + '/contents/.ci/run?ref=' + FIRST] = encoded('RED-testing ' + 'f'*40 + '\n')
    self.assertFalse(self.verify(responses))

  def test_retry_marker_parent_mismatch_is_rejected(self):
    responses = deepcopy(self.responses)
    responses[BASE + '/contents/.ci/run?ref=' + RETRY] = encoded('GREEN-testing ' + CANDIDATE + '\n')
    self.assertFalse(self.verify(responses))

  def test_missing_provider_history_is_rejected(self):
    responses = deepcopy(self.responses)
    del responses[BASE + '/commits/' + PUBLISHED]
    self.assertFalse(self.verify(responses))
