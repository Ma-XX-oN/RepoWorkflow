from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

def digest(text): return hashlib.sha256(text.encode("utf-8")).hexdigest()
def gh(*args):
  p=subprocess.run(["gh", *args], text=True, capture_output=True)
  if p.returncode:
    print((p.stderr or p.stdout).strip(), file=sys.stderr); raise SystemExit(p.returncode)
  return p.stdout

def read_body(issue):
  value=json.loads(gh("issue", "view", str(issue), "--json", "body"))
  body=value.get("body")
  if not isinstance(body, str): raise SystemExit("GitHub returned invalid issue body")
  return body

def main():
  args=sys.argv[1:]
  if len(args)!=6 or args[:3] != ["issue", "body", "replace"]:
    raise SystemExit("usage: github-ticket-adapter issue body replace ISSUE EXPECTED_DIGEST BODY_FILE")
  issue=int(args[3]); expected=args[4]; path=Path(args[5]); new=path.read_text(encoding="utf-8")
  current=read_body(issue)
  if digest(current)!=expected:
    raise SystemExit("ticket body changed since review")
  gh("issue", "edit", str(issue), "--body-file", str(path))
  confirmed=read_body(issue)
  if confirmed!=new:
    raise SystemExit("ticket body replacement outcome is unknown")
  print(json.dumps({"schema_version":1,"number":issue,"body_digest":digest(confirmed)}))

if __name__ == "__main__": main()
