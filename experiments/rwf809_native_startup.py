#!/usr/bin/env python3
"""RWF #809 isolated native Git process/FS benchmark; no product changes."""
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

def run(args, cwd=None, env=None):
  start = time.perf_counter_ns()
  p = subprocess.run(args, cwd=cwd, env=env, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE, check=False, timeout=25)
  ms = (time.perf_counter_ns() - start) / 1_000_000
  if p.returncode:
    raise RuntimeError(f"{args!r}: {p.returncode}: {p.stderr.decode('utf-8', 'replace')[:500]}")
  return ms

def meta(args):
  p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=25)
  return dict(exit_code=p.returncode, stdout=p.stdout.decode("utf-8", "replace").strip(),
              stderr=p.stderr.decode("utf-8", "replace").strip())

def percentiles(values):
  a = sorted(values)
  return dict(n=len(a), median_ms=statistics.median(a),
              p95_ms=a[min(len(a)-1, int(len(a)*.95))],
              mean_ms=statistics.mean(a), min_ms=a[0], max_ms=a[-1])

def main():
  root = Path.cwd()
  git = shutil.which("git")
  if not git:
    raise RuntimeError("git executable not found")
  with tempfile.TemporaryDirectory(prefix="rwf809-") as d:
    repo = Path(d) / "small"
    repo.mkdir()
    run([git, "init", "-q", str(repo)])
    for i in range(100):
      (repo / f"f{i:03}.txt").write_text("fixed fixture\n", encoding="utf-8")
    run([git, "-C", str(repo), "add", "."])
    run([git, "-C", str(repo), "-c", "user.name=RWF", "-c", "user.email=rwf@example.invalid",
         "commit", "-qm", "fixture"])
    launcher = ["cmd.exe", "/d", "/c", "exit", "0"] if os.name == "nt" else ["/bin/true"]
    commands = {
      "native_nop": launcher,
      "python_nop": [sys.executable, "-c", "pass"],
      "git_version": [git, "--version"],
      "git_rev_parse_small": [git, "-C", str(repo), "rev-parse", "--is-inside-work-tree"],
      "git_status_small": [git, "-C", str(repo), "status", "--porcelain"],
      "git_status_rwf": [git, "-C", str(root), "status", "--porcelain"],
      "git_status_small_no_fsmonitor": [git, "-c", "core.fsmonitor=false",
                                        "-C", str(repo), "status", "--porcelain"]
    }
    # Compare Git for Windows executable entry paths separately; launcher wrappers
    # are a different variable from repository size or filesystem performance.
    if os.name == "nt":
      pf = os.environ.get("ProgramFiles", "C:\\Program Files")
      for name, rel in (("cmd", "cmd/git.exe"), ("bin", "bin/git.exe"),
                        ("mingw64", "mingw64/bin/git.exe")):
        alternative = Path(pf) / "Git" / rel
        if alternative.is_file() and str(alternative).lower() != str(git).lower():
          commands[f"git_version_{name}"] = [str(alternative), "--version"]
          commands[f"git_status_small_{name}"] = [
            str(alternative), "-C", str(repo), "status", "--porcelain"]
    # Interleave operations to reduce monotonic thermal / contention bias.
    raw = {name: [] for name in commands}
    for repetition in range(120):
      keys = list(commands)
      if repetition % 2:
        keys.reverse()
      for name in keys:
        raw[name].append(run(commands[name]))
    fs_raw = []
    p = Path(d) / "fsprobe"
    for i in range(1000):
      start = time.perf_counter_ns()
      p.write_bytes(b"x" * 4096)
      if p.read_bytes() != b"x" * 4096:
        raise RuntimeError("filesystem read mismatch")
      p.unlink()
      fs_raw.append((time.perf_counter_ns() - start) / 1_000_000)
    data = {
      "experiment": "RWF-809-native-startup-1", "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "platform": platform.platform(), "os": os.name, "python": sys.version,
      "git_executable": git, "git_version": meta([git, "--version"]),
      "commit": meta([git, "rev-parse", "HEAD"]),
      "autocrlf": meta([git, "config", "--show-origin", "--get", "core.autocrlf"]),
      "config_allowlist": {k: meta([git, "config", "--show-origin", "--get", k])
                          for k in ("core.autocrlf", "core.fsmonitor", "core.filemode",
                                    "core.ignorecase")},
      "cpu_count": os.cpu_count(), "operations": {k:percentiles(v) for k,v in raw.items()},
      "filesystem_4k_write_read_unlink": percentiles(fs_raw), "samples_ms":raw,
      "fs_samples_ms":fs_raw,
    }
  out = Path("rwf809-results")
  out.mkdir(exist_ok=True)
  (out / f"{platform.system().lower()}.json").write_text(json.dumps(data,indent=2),encoding="utf-8")
  print(json.dumps({k:v for k,v in data.items() if k not in ("samples_ms","fs_samples_ms","system")},indent=2))

if __name__ == "__main__":
  main()
