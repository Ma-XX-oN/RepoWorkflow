import copy
import json
from pathlib import Path
import tempfile
import unittest

from repo_workflow.github_result_transport import (
  TransportError, fetch_bundle, publish_bundle,
)


REQUEST = {
  "contract_version": 1,
  "operation": "publish",
  "invocation_id": "invoke-1",
  "candidate": {"repository": "owner/repo", "commit": "a" * 40, "base": "b" * 40},
  "requirements": {"artifacts": ["result", "logs"]},
}
RECORDS = {"result": b'{"outcome":"failed"}', "logs": b"binary\x00log"}


class GithubResultTransportTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.directory = Path(self.temp.name) / "bundle"

  def fetch(self, request=REQUEST, names=None):
    if names is None:
      names = request["requirements"]["artifacts"]
    return fetch_bundle(self.directory, request["invocation_id"],
                        request["candidate"], names)

  def test_exact_binary_roundtrip_and_repeat_fetch(self):
    publish_bundle(REQUEST, RECORDS, self.directory)
    self.assertEqual(self.fetch(), RECORDS)
    self.assertEqual(self.fetch(), RECORDS)

  def test_zero_and_one_artifact(self):
    for contents in ({}, {"result": b"x"}):
      with self.subTest(contents=contents):
        request = copy.deepcopy(REQUEST)
        request["requirements"]["artifacts"] = list(contents)
        path = self.directory / str(len(contents))
        publish_bundle(request, contents, path)
        self.assertEqual(fetch_bundle(path, request["invocation_id"],
                         request["candidate"], list(contents)), contents)

  def test_missing_bundle_and_corrupt_manifest(self):
    with self.assertRaises(TransportError):
      self.fetch()
    publish_bundle(REQUEST, RECORDS, self.directory)
    (self.directory / "manifest.json").write_text("invalid")
    with self.assertRaises(TransportError):
      self.fetch()

  def test_tampered_artifact(self):
    publish_bundle(REQUEST, RECORDS, self.directory)
    (self.directory / "result").write_bytes(b'{"outcome":"passed"}')
    with self.assertRaisesRegex(TransportError, "integrity"):
      self.fetch()

  def test_missing_and_extra_artifact(self):
    publish_bundle(REQUEST, RECORDS, self.directory)
    (self.directory / "result").unlink()
    with self.assertRaises(TransportError):
      self.fetch()
    (self.directory / "result").write_bytes(RECORDS["result"])
    (self.directory / "undeclared").write_bytes(b"x")
    with self.assertRaises(TransportError):
      self.fetch()

  def test_changed_repository_commit_base_and_invocation(self):
    publish_bundle(REQUEST, RECORDS, self.directory)
    for key in ("commit", "base", "repository"):
      candidate = dict(REQUEST["candidate"])
      candidate[key] += "changed"
      with self.assertRaisesRegex(TransportError, "identity"):
        fetch_bundle(self.directory, REQUEST["invocation_id"], candidate,
                     REQUEST["requirements"]["artifacts"])
    with self.assertRaisesRegex(TransportError, "identity"):
      fetch_bundle(self.directory, "invoke-2", REQUEST["candidate"],
                   REQUEST["requirements"]["artifacts"])

  def test_conflicting_and_duplicate_publish_rejected(self):
    publish_bundle(REQUEST, RECORDS, self.directory)
    for records in (RECORDS, {**RECORDS, "result": b"changed"}):
      with self.assertRaises(TransportError):
        publish_bundle(REQUEST, records, self.directory)
    self.assertEqual(self.fetch(), RECORDS)

  def test_unsafe_names_and_undeclared_records(self):
    for name in ("../bad", "/tmp/bad", "..", "a/b"):
      request = copy.deepcopy(REQUEST)
      request["requirements"]["artifacts"] = [name]
      with self.assertRaises(TransportError):
        publish_bundle(request, {name: b"x"}, self.directory)
      self.assertFalse(self.directory.exists())
    with self.assertRaises(TransportError):
      publish_bundle(REQUEST, {"result": b"x"}, self.directory)

  def test_invalid_envelopes(self):
    for key, value in (
      ("contract_version", 2), ("contract_version", True),
      ("operation", "fetch"), ("candidate", None), ("requirements", None),
      ("invocation_id", "../unsafe"),
    ):
      with self.subTest(key=key, value=value):
        request = copy.deepcopy(REQUEST)
        request[key] = value
        with self.assertRaises(TransportError):
          publish_bundle(request, RECORDS, self.directory)
    self.assertFalse(self.directory.exists())

  def test_manifest_duplicate_and_extra_fields(self):
    publish_bundle(REQUEST, RECORDS, self.directory)
    path = self.directory / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["artifacts"] = [manifest["artifacts"][0]] * 2
    path.write_text(json.dumps(manifest))
    with self.assertRaises(TransportError):
      self.fetch()
    manifest["unexpected"] = True
    path.write_text(json.dumps(manifest))
    with self.assertRaises(TransportError):
      self.fetch()


if __name__ == "__main__":
  unittest.main()
