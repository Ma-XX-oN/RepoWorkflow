"""Native rwf done patch/minor/major accepts verified completion only."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_workflow.done_cli import DoneCommandError,execute_done_command
from repo_workflow.done_provider_pipeline import (
  DeferredProviderAttempt,FailedProviderAttempt,
)
from repo_workflow.done_runtime import (
  VerifiedNativeDone,VerifiedDeferredDone,VerifiedFailedDone,
)
from repo_workflow.done_shared_lifecycle import (
  SharedLifecycleEvidence,SharedAuthorityObservation,
)
from repo_workflow.done_failure_handoff import (
  FailureHandoff,PersistedFailureHandoff,
)
from repo_workflow.integration_coordination import MitDeferredEvent
from repo_workflow.public_commands import COMMANDS,PUBLIC_COMMANDS
from repo_workflow.public_cli import handle_public
from repo_workflow.command_grammar import Context
from tests.test_done_completion import CompletionTests


class CommandTests(unittest.TestCase):
  def setUp(self):
    self.fixture=CompletionTests(
      "test_done_only_after_both_refs_and_provenance")
    self.fixture.setUp()
    self.messages=[]
    self.called=[]

  def native(self,completion):
    shared=SharedLifecycleEvidence(
      "Org/Repo","authoritative-state","a"*40,123,
      completion.lifecycle["revision"],completion.operation_id,
      completion.terminal.accepted_sha,completion.landed_sha,
      "b"*64,"c"*64,True)
    authority=SharedAuthorityObservation(
      "Org/Repo","authoritative-state","a"*40,True)
    return VerifiedNativeDone(completion,shared,authority)

  def run_command(self,release="patch",outcome=None):
    if outcome is None:
      outcome=self.native(self.fixture.invoke())
    def executor(version):
      self.called.append(version)
      return outcome
    return execute_done_command(
      release,trusted_executor=executor,emit=self.messages.append)

  def test_native_public_dispatch_to_injected_verifier(self):
    root=Path(".")
    general=Context(root,legal_only=False)
    with (patch("repo_workflow.public_cli._diagnose",
                return_value=(general,general,None,None,None,None)),
          patch("repo_workflow.public_cli.configure_ticket_merge_driver"),
          patch("repo_workflow.public_cli.ensure_public_runtime_identity"),
          patch("builtins.print") as printed):
      exit_code=handle_public(
        root,["done","patch"],engine_root=root,
        done_executor=lambda release:self.native(self.fixture.invoke()))
    self.assertEqual(exit_code,0)
    self.assertEqual(json.loads(printed.call_args.args[0])["status"],"DONE")

  def test_native_public_dispatch_without_authority_refuses_success(self):
    root=Path(".")
    general=Context(root,legal_only=False)
    with (patch("repo_workflow.public_cli._diagnose",
                return_value=(general,general,None,None,None,None)),
          patch("repo_workflow.public_cli.configure_ticket_merge_driver"),
          patch("repo_workflow.public_cli.ensure_public_runtime_identity")):
      with self.assertRaisesRegex(DoneCommandError,"authority"):
        handle_public(root,["done","patch"],engine_root=root)

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
      self.run_command(outcome=self.native(changed))
    self.assertEqual(self.messages,[])

  def test_bare_provider_completion_cannot_claim_native_done(self):
    with self.assertRaisesRegex(DoneCommandError,"unverified"):
      self.run_command(outcome=self.fixture.invoke())
    self.assertEqual(self.messages,[])

  def test_mismatched_shared_lifecycle_proof_cannot_claim_done(self):
    from dataclasses import replace
    outcome=self.native(self.fixture.invoke())
    for altered in (
      replace(outcome,authority=replace(
        outcome.authority,commit_sha="f"*40)),
      replace(outcome,shared=replace(
        outcome.shared,operation_id="other-operation")),
      replace(outcome,shared=replace(
        outcome.shared,independently_authenticated=False))):
      with self.subTest(altered=altered):
        with self.assertRaisesRegex(DoneCommandError,
                                    "shared canonical authority"):
          self.run_command(outcome=altered)
    self.assertEqual(self.messages,[])

  def test_failed_or_deferred_never_return_done(self):
    ready=self.fixture.accepted.ready
    deferred=DeferredProviderAttempt(ready,"mit-timeout-proof",2)
    with self.assertRaisesRegex(DoneCommandError,"unverified"):
      self.run_command(outcome=deferred)
    self.assertEqual(self.messages,[])
    evidence=MitDeferredEvent(
      ready.guid,ready.destination,ready.sha,1,"mit-timeout-proof","timeout")
    self.assertEqual(self.run_command(
      outcome=VerifiedDeferredDone(deferred,evidence)),3)
    self.assertEqual(json.loads(self.messages[-1])["status"],
                     "MIT_TIMEOUT_DEFERRED")
    self.messages.clear()
    failed=FailedProviderAttempt(ready,"AIT","provider-failure",2)
    self.messages.clear()
    with self.assertRaisesRegex(DoneCommandError,"unverified"):
      self.run_command(outcome=failed)
    self.assertEqual(self.messages,[])
    evidence=FailureHandoff(
      ready.guid,123,ready.destination,ready.sha,"b"*40,"c"*40,
      "AIT_FAIL","provider-failure",(123,),"repro",(),"owner uncertain",
      "provider-op-1")
    persisted=PersistedFailureHandoff(
      evidence,((123,"issue-comment-1"),))
    self.assertEqual(self.run_command(
      outcome=VerifiedFailedDone(failed,persisted)),4)
    self.assertEqual(json.loads(self.messages[-1])["status"],
                     "FAILED_STAGE")

  def test_untrusted_pass_flag_never_counts_success(self):
    with self.assertRaisesRegex(DoneCommandError,"unverified"):
      self.run_command(outcome=True)
    self.assertEqual(self.messages,[])


if __name__=="__main__":
  unittest.main()
