"""Launch a pinned RWF test under the read-only #809 profiler portably."""
from pathlib import Path
import os
import subprocess
import sys


def main() -> int:
  if len(sys.argv) < 3:
    raise SystemExit("usage: launch.py TARGET [script|module] [arguments...]")
  target = Path(sys.argv[1]).resolve()
  if not (target / "scripts" / "validate.py").is_file():
    raise RuntimeError("target is not a valid RWF checkout")
  profiler_dir = Path(__file__).resolve().parent
  if not (profiler_dir / "sitecustomize.py").is_file():
    raise RuntimeError("profiler source unavailable")
  env = os.environ.copy()
  old = env.get("PYTHONPATH", "")
  paths = [str(profiler_dir), str(target)]
  if old:
    paths.append(old)
  env["PYTHONPATH"] = os.pathsep.join(paths)
  env["RWF809_TRACE_DIR"] = str(Path.cwd() / "rwf809-process-logs")
  kind = sys.argv[2]
  if kind == "regression":
    args = [sys.executable, "scripts/validate.py"]
  elif kind == "module":
    if len(sys.argv) != 4:
      raise RuntimeError("exactly one unittest module required")
    args = [sys.executable, "-m", "unittest", sys.argv[3], "-v"]
  else:
    raise RuntimeError("unknown profile test kind")
  return subprocess.run(args, cwd=target, env=env, check=False).returncode


if __name__ == "__main__":
  raise SystemExit(main())
