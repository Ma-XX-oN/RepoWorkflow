"""Read-only GitHub protection survey for an explicit repository.

No mutation endpoints are used. Requires GITHUB_TOKEN for authenticated reads.
A 403/404 never establishes that branch or tag protection is absent.
"""

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ENDPOINTS = {
  "repository": "/repos/{repo}",
  "main": "/repos/{repo}/branches/main",
  "rulesets": "/repos/{repo}/rulesets",
  "protection": "/repos/{repo}/branches/main/protection",
}


def inspect(repo, token, transport=urlopen):
  """Return policy read status and minimal public configuration evidence."""
  if not isinstance(repo, str) or repo.count("/") != 1:\n    raise ValueError("invalid repository name")\n  if not all(part and part.replace("-", "").replace("_", "").isalnum()\n             for part in repo.split("/")):\n    raise ValueError("invalid repository path")\n  results = {}
  for key, template in ENDPOINTS.items():
    url = "https://api.github.com" + template.format(repo=repo)
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "RepoWorkflow-627-read-only"}
    if token:
      headers["Authorization"] = "Bearer " + token
    request = Request(url, headers=headers, method="GET")
    try:
      with transport(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
        status = response.status
    except HTTPError as exc:
      results[key] = {"status": exc.code, "classification": "INCOMPLETE"}
      continue
    except (URLError, OSError, ValueError, UnicodeError) as exc:
      results[key] = {"status": None, "classification": "INCOMPLETE",
                      "error": type(exc).__name__}
      continue
    record = {"status": status, "classification": "OBSERVED"}
    if key == "repository" and isinstance(payload, dict):
      record["id"] = payload.get("id")
      record["default_branch"] = payload.get("default_branch")
      record["caller_permissions"] = payload.get("permissions")
    if key == "main" and isinstance(payload, dict):
      record["protected"] = payload.get("protected")
      record["protection_enabled"] = (
        (payload.get("protection") or {}).get("enabled"))
      record["sha"] = (payload.get("commit") or {}).get("sha")
    if key == "rulesets" and isinstance(payload, list):
      record["ruleset_ids"] = [row.get("id") for row in payload
                               if isinstance(row, dict)]
    if key == "protection" and isinstance(payload, dict):
      record["protection_keys"] = sorted(payload.keys())
    results[key] = record
  return results


def main():
  repo = sys.argv[1] if len(sys.argv) == 2 else ""
  if not repo:
    print("usage: python scripts/probe-provider-protection.py OWNER/REPO",
          file=sys.stderr)
    return 2
  result = inspect(repo, os.environ.get("GITHUB_TOKEN", ""))
  print(json.dumps(result, sort_keys=True, indent=2))
  return 0


if __name__ == "__main__":
  sys.exit(main())
