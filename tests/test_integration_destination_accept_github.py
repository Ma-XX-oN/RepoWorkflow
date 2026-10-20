"""Provider-native exact-old destination CAS; no unapproved remote updates."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adapters.repo_host_github_integration_accept import (
  AcceptanceProviderError, accept_destination, _validate,
)
from repo_workflow.integration_host_v2 import IntegrationHost, IntegrationHostError

REPO="Org/Repo"
GUID="11111111-1111-4111-8111-111111111111"
OLD="a"*40
NEW="b"*40
SOURCE="c"*40
REF="refs/heads/INT-ATTEMPT-issue-681/target-"+GUID


def record(**kw):
  data={
    "repository":REPO,"destination":"target",
    "int_attempt_ref":REF,"accepted_sha":SOURCE,
    "expected_destination_sha":OLD,"proposed_sha":NEW,
    "guid":GUID,"lease_generation":9,"holder":"worker-one",
    "authorization_ref":"signed-approved","evidence_ref":"tested-source",
    "operation_id":"accept-once",
  }
  data.update(kw)
  return data


def request(**kw):
  return {"schema_version":2,"repository":REPO,
          "operation":"destination.accept","request_id":"accept-once",
          "parameters":{"record":record(**kw)}}


class Backend:
  repository=REPO


def accepted_request(*,observed=NEW,returncode=0,verify=lambda _:True,
                     snapshot=OLD,lease=True,source=SOURCE,ancestor=True,
                     intent_exists=False):
  reply=request()
  proof={"destination":"target","generation":9,
         "holder":"worker-one","guid":GUID}
  successful=SimpleNamespace(returncode=0)
  calls=[]
  state={"pushed":False,"intent":{"bound":True} if intent_exists else None}

  def git(root,*argv):
    calls.append(argv)
    if argv[0]=="cat-file":
      return successful
    if argv[0]=="merge-base":
      return SimpleNamespace(returncode=0 if ancestor else 1)
    if argv[0]=="push":
      state["pushed"]=True
      return SimpleNamespace(returncode=returncode)
    raise AssertionError(argv)

  def sha(backend,ref):
    if ref==REF:
      return source
    if ref=="refs/heads/target":
      return observed if state["pushed"] else snapshot
    raise AssertionError(ref)

  def publish(backend,request):
    state["intent"]={"bound":True}
    return state["intent"]

  with (patch("adapters.repo_host_github_integration_accept._remote_scope",
              return_value="https://github.com/Org/Repo.git"),
        patch("adapters.repo_host_github_integration_accept.read_lease",
              return_value=proof if lease else {**proof,"generation":10}),
        patch("adapters.repo_host_github_integration_accept.read_destination_snapshot",
              return_value={"sha":snapshot}),
        patch("adapters.repo_host_github_integration_accept._sha",
              side_effect=sha),
        patch("adapters.repo_host_github_integration_accept._git",
              side_effect=git),
        patch("adapters.repo_host_github_integration_accept.read_intent",
              side_effect=lambda backend,request:state["intent"]),
        patch("adapters.repo_host_github_integration_accept.publish_intent",
              side_effect=publish)):
    answer=accept_destination(Backend(),reply,Path("/sandbox"),"origin",
                              verify_evidence=verify)
  return answer,calls

class DestinationAcceptanceTests(unittest.TestCase):
  def test_correct_atomic_acceptance_has_exact_receipt(self):
    (status,receipt),calls=accepted_request()
    self.assertEqual(status,"applied")
    self.assertEqual(receipt,{"destination":"target","expected_sha":OLD,
                               "landed_sha":NEW,"operation_id":"accept-once"})
    cmd=next(c for c in calls if c[0]=="push")
    self.assertIn("--force-with-lease=refs/heads/target:"+OLD,cmd)
    self.assertIn(NEW+":refs/heads/target",cmd)

  def test_missing_external_verifier_refuses(self):
    with self.assertRaisesRegex(AcceptanceProviderError,"evidence"):
      accept_destination(Backend(),request(),Path("/tmp"),"origin",
                         verify_evidence=None)

  def test_changed_lease_destination_source_ancestry_refuse(self):
    for changes,word in [
      ({"lease":False},"lease"),
      ({"snapshot":"d"*40},"current destination"),
      ({"source":"e"*40},"attempt source"),
      ({"ancestor":False},"descendant"),
    ]:
      with self.subTest(changes=changes):
        with self.assertRaisesRegex(AcceptanceProviderError,word):
          accepted_request(**changes)

  def test_remote_ack_loss_reconciles_exact_persisted_operation(self):
    (status,receipt),calls=accepted_request(returncode=1)
    self.assertEqual(status,"unchanged")
    self.assertEqual(receipt["operation_id"],"accept-once")
    self.assertEqual(sum(c[0]=="push" for c in calls),1)
    with self.assertRaisesRegex(AcceptanceProviderError,"UNKNOWN"):
      accepted_request(observed="f"*40)

  def test_revocation_after_intent_before_provider_push(self):
    calls={"count":0}
    def verifier(record):
      calls["count"]+=1
      return calls["count"]==1
    with self.assertRaisesRegex(AcceptanceProviderError,"revoked"):
      accepted_request(verify=verifier)
    self.assertEqual(calls["count"],2)

  def test_crash_restart_readback_without_second_push(self):
    (status,receipt),calls=accepted_request(
      snapshot=NEW,observed=NEW,intent_exists=True)
    self.assertEqual(status,"unchanged")
    self.assertEqual(receipt["landed_sha"],NEW)
    self.assertFalse(any(c[0]=="push" for c in calls))
    with self.assertRaisesRegex(AcceptanceProviderError,"without persisted"):
      accepted_request(snapshot=NEW,observed=NEW)
    with self.assertRaisesRegex(AcceptanceProviderError,"destination differs"):
      accepted_request(snapshot="d"*40,intent_exists=True)

  def test_reject_forged_or_stale_fields(self):
    for kw in ({"repository":"Foreign/Repo"},
               {"destination":"../target"},
               {"lease_generation":True},
               {"operation_id":"wrong-id"},
               {"int_attempt_ref":REF.replace("target","wrong")},
               {"proposed_sha":OLD},
               {"evidence_ref":""},
               {"authorization_ref":""}):
      with self.subTest(kw=kw):
        self.assertRaises(AcceptanceProviderError,_validate,
                          request(**kw),REPO)

  def test_provider_neutral_reply_identity_and_request_validation(self):
    def transport(value):
      data=value["parameters"]["record"]
      return {
        "schema_version":2,"repository":REPO,"operation":"destination.accept",
        "request_id":value["request_id"],"status":"applied",
        "result":{"destination":data["destination"],
                  "expected_sha":data["expected_destination_sha"],
                  "landed_sha":data["proposed_sha"],
                  "operation_id":data["operation_id"]}}
    host=IntegrationHost(REPO,transport)
    self.assertEqual(host.request("destination.accept","accept-once",
                     {"record":record()})["landed_sha"],NEW)
    for bad in (record(repository="Foreign/Repo"),
                record(operation_id="different"),
                record(lease_generation=True)):
      with self.assertRaises(IntegrationHostError):
        host.request("destination.accept","accept-once",{"record":bad})


if __name__=="__main__":
  unittest.main()
