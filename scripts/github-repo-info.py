from __future__ import annotations

import hashlib
import json
import subprocess
import sys

def gh(*args):
  result=subprocess.run(["gh",*args],text=True,capture_output=True)
  if result.returncode:
    print((result.stderr or result.stdout).strip(),file=sys.stderr); raise SystemExit(result.returncode)
  try: return json.loads(result.stdout)
  except json.JSONDecodeError as error: raise SystemExit(f"gh returned malformed JSON: {error}")

def normalize_issue(value):
  state=value.get("state")
  if isinstance(state,str): state=state.lower()
  return {"schema_version":1,"number":value["number"],"title":value["title"],"state":state}

def normalize_body(number, body):
  return {"schema_version":1,"number":number,"body":body,"body_digest":hashlib.sha256(body.encode("utf-8")).hexdigest()}

def main(args=None):
  args=list(sys.argv[1:] if args is None else args)
  if args==["repository"]:
    value=gh("repo","view","--json","nameWithOwner")
    print(json.dumps({"schema_version":1,"repository":value["nameWithOwner"],"provider":"github"})); return
  if len(args)==3 and args[:2]==["issue","get"]:
    number=int(args[2]); value=gh("issue","view",str(number),"--json","number,title,state")
    print(json.dumps(normalize_issue(value))); return
  if args==["issue","list-open"]:
    values=gh("issue","list","--state","open","--limit","1000","--json","number,title")
    issues=sorted(({"number":x["number"],"title":x["title"]} for x in values),key=lambda x:x["number"])
    print(json.dumps({"schema_version":1,"issues":issues})); return
  if len(args)==3 and args[:2]==["issue","body"]:
    number=int(args[2]); value=gh("issue","view",str(number),"--json","body")
    body=value.get("body")
    if not isinstance(body,str): raise SystemExit("GitHub returned invalid issue body")
    print(json.dumps(normalize_body(number,body))); return
  raise SystemExit("unsupported repo-info operation")

if __name__=="__main__": main()
