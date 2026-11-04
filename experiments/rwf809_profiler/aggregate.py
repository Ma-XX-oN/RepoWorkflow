"""Summarize sanitized per-PID process traces from RWF 809 without raw arguments."""
import collections
import json
import os
from pathlib import Path
import sys

def main():
  if len(sys.argv) != 3:
    raise SystemExit("usage: aggregate.py TRACE_DIRECTORY OUTPUT_FILE")
  source = Path(sys.argv[1])
  output = Path(sys.argv[2])
  if not source.is_dir():
    raise SystemExit("missing trace directory")
  total = collections.Counter()
  by_op = collections.defaultdict(lambda: [0, 0.0])
  by_caller = collections.defaultdict(lambda: [0, 0.0])
  by_test = collections.defaultdict(lambda: [0, 0.0])
  git_count = 0
  rows = []
  for p in sorted(source.glob("process-*.jsonl")):
    for line in p.read_text(encoding="utf-8").splitlines():
      if line.strip():
        rows.append(json.loads(line))
  parents = {r["child_pid"]: r["parent_pid"] for r in rows if r.get("child_pid")}
  owner = {r["child_pid"]: r["test"] for r in rows if r.get("child_pid") and r.get("test")}
  def owning_test(record):
    if record.get("test"):
      return record["test"]
    pid = record.get("parent_pid")
    seen = set()
    while pid is not None and pid not in seen:
      seen.add(pid)
      if pid in owner:
        return owner[pid]
      pid = parents.get(pid)
    return "setup-or-child-process"
  for x in rows:
      kind = x["kind"]
      total[kind] += 1
      if kind != "git":
        continue
      git_count += 1
      for mapping, key in ((by_op, x["operation"]), (by_caller, x["caller"]),
                           (by_test, owning_test(x))):
        record = mapping[key]
        record[0] += 1
        record[1] += float(x["elapsed_ms"])

  def top(mapping):
    return [{"label": k, "calls": v[0], "cumulative_wait_ms": round(v[1], 3)}
            for k,v in sorted(mapping.items(), key=lambda x: (-x[1][1], x[0]))[:80]]

  result = {"profile": "RWF-809-current-assembled-catalogue", "total_counts": dict(total),
            "git_calls": git_count, "by_git_operation": top(by_op),
            "by_python_callsite": top(by_caller), "by_test": top(by_test),
            "trace_files": len(list(source.glob("process-*.jsonl"))),
            "method": "Python subprocess.Popen sitecustomize wrapper; counts observed direct children; excludes native grandchildren and subprocess bypasses; profiling overhead included"}
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
  print(json.dumps(result, indent=2))


if __name__ == "__main__":
  main()
