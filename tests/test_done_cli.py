"""Native rwf done patch/minor/major accepts verified completion only."""
import json
import unittest

from repo_workflow.done_cli import DoneCommandError,execute_done_command
from repo_workflow.done_provider_pipeline import (
  DeferredProviderAttempt,FailedProviderAttempt,
)
from repo_workflow.public_commands import COMMANDS,PUBLIC_COMMANDS
from tests.test_done_completion import CompletionTests


class CommandTests(unittest.TestCase):
  def setUp(self):
    self.fixture=CompletionTests(
      "test_done_only_after_both_refs_and_provenance")
    self.fixture.setUp()
    self.messages=[]
    self.called=[]

  def run_command(self,release="patch",outcome=None):
    if outcome is None:
      outcome=self.fixture.invoke()
    def executor(version):
      self.called.append(version)
      return outcome
    return execute_done_command(
      release,trusted_executor=executor,emit=self.messages.append)

  def test_native_command_is_registered_for_three_semvers(self):
    self.assertIn("done",PUBLIC_COMMANDS)
    self.assertEqual(set(COMMANDS["done"]),
                     {"patch","minor","major"})

  def test_three_release_kinds_require_verified_completion(self):
    for name in ("patch","minor","major"):
      self.messages.clear()
      self.assertEqual(self.run_command(name),0)
      result=json.loads(self.messages[-1])
      self.assertEqual(result["status"],"DONE")
      self.assertEqual(result["release"],name)
      self.assertEqual(result["operation_id"],"op-1")

  def test_missing_authenticated_executor_is_not_success(self):
    for name in ("patch","minor","major"):
      with self.subTest(release=name):
        with self.assertRaisesRegex(
            DoneCommandError,"authority is unavailable"):
          execute_done_command(
            name,trusted_executor=None,emit=self.messages.append)
    self.assertEqual(self.messages,[])

  def test_invalid_release_refused_before_callback(self):
    with self.assertRaisesRegex(DoneCommandError,"requires patch"):
      self.run_command("release")
    self.assertEqual(self.called,[])
    self.assertEqual(self.messages,[])

  def test_host_timeout_requires_readback_not_success(self):
    def fail(release):
      raise TimeoutError("provider response unknown")
    with self.assertRaisesRegex(DoneCommandError,"UNKNOWN"):
      execute_done_command(
        "patch",trusted_executor=fail,emit=self.messages.append)
    self.assertEqual(self.messages,[])

  def test_forged_completion_without_retirement_refused(self):
    from dataclasses import replace
    original=self.fixture.invoke()
    changed=replace(original,retired=original.retired[:1])
    with self.assertRaisesRegex(
        DoneCommandError,"not certified"):
      self.run_command(outcome=changed)
    self.assertEqual(self.messages,[])

  def test_failed_or_deferred_never_return_done(self):
    ready=self.fixture.accepted.ready
    deferred=DeferredProviderAttempt(ready,"mit-timeout-proof",2)
    self.assertEqual(self.run_command(outcome=deferred),3)
    self.assertEqual(json.loads(self.messages[-1])["status"],
                     "MIT_TIMEOUT_DEFERRED")
    self.messages.clear()
    failed=FailedProviderAttempt(ready,"AIT","provider-failure",2)
    self.assertEqual(self.run_command(outcome=failed),4)
    self.assertEqual(json.loads(self.messages[-1])["status"],
                     "FAILED_STAGE")

  def test_untrusted_pass_flag_never_counts_success(self):
    with self.assertRaisesRegex(DoneCommandError,"unverified"):
      self.run_command(outcome=True)
    self.assertEqual(self.messages,[])


if __name__=="__main__":
  unittest.main()
