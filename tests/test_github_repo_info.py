import hashlib
import importlib.util
from pathlib import Path
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/"scripts"/"github-repo-info.py"
spec=importlib.util.spec_from_file_location("github_repo_info",SCRIPT)
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)

class GithubRepoInfoTests(unittest.TestCase):
  def test_issue_normalization(self):
    self.assertEqual(module.normalize_issue({"number":7,"title":"T","state":"OPEN"}),{"schema_version":1,"number":7,"title":"T","state":"open"})
  def test_body_digest_is_exact_utf8(self):
    body="é\n"
    value=module.normalize_body(7,body)
    self.assertEqual(value["body"],body)
    self.assertEqual(value["body_digest"],hashlib.sha256(body.encode("utf-8")).hexdigest())

if __name__=="__main__": unittest.main()
