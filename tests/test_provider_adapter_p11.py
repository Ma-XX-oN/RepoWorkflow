from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPO_INFO = ROOT / "adapters" / "repo-info-github.py"
DEPENDENCIES = ROOT / "scripts" / "github-ticket-dependencies.py"


class GitHubProviderBoundaryP11Tests(unittest.TestCase):
  def fake_gh(self, root: Path) -> tuple[Path, Path]:
    bindir = root / "bin"
    bindir.mkdir()
    script = root / "fake_gh.py"
    log = root / "provider-argv.jsonl"
    script.write_text(
      "import json, os, sys\n"
      "args = sys.argv[1:]\n"
      "log = os.environ['P11_LOG']\n"
      "with open(log, 'a', encoding='utf-8') as handle:\n"
      "  handle.write(json.dumps(args) + '\\n')\n"
      "mode = os.environ['P11_MODE']\n"
      "def require(expected):\n"
      "  if args != expected:\n"
      "    sys.stderr.write('unexpected provider argv: ' + repr(args) + '\\n')\n"
      "    raise SystemExit(91)\n"
      "repo = ['issue', 'view', '64', '--json', "
      "'number,title,state,url', '--repo', 'o/r']\n"
      "dependency = ['issue', 'view', '64', '--json', 'blockedBy']\n"
      "related = ['issue', 'view', '64', '--json', 'blockedBy,blocking']\n"
      "if mode == 'repo-unicode':\n"
      "  require(repo)\n"
      "  value = {'number': 64, 'title': 'München → 東京', "
      "'state': 'OPEN', 'url': 'https://example.invalid/issues/64'}\n"
      "  sys.stdout.buffer.write(json.dumps(value, ensure_ascii=False).encode('utf-8'))\n"
      "elif mode == 'dependency-related':\n"
      "  require(related)\n"
      "  value = {\n"
      "    'blockedBy': {'nodes': [{'number': 2}], 'totalCount': 1},\n"
      "    'blocking': {'nodes': [{'number': 70}], 'totalCount': 1},\n"
      "  }\n"
      "  sys.stdout.buffer.write(json.dumps(value).encode('utf-8'))\n"
      "elif mode in {'repo-error', 'dependency-error'}:\n"
      "  require(repo if mode == 'repo-error' else dependency)\n"
      "  sys.stderr.buffer.write('provider café → 東京\\n'.encode('utf-8'))\n"
      "  raise SystemExit(7)\n"
      "elif mode == 'repo-cp1252':\n"
      "  require(repo)\n"
      "  sys.stdout.buffer.write("
      "b'{\"number\":64,\"title\":\"caf\\xe9\",\"state\":\"OPEN\","
      "\"url\":\"https://example.invalid/issues/64\"}')\n"
      "elif mode == 'dependency-cp1252':\n"
      "  require(dependency)\n"
      "  sys.stdout.buffer.write("
      "b'{\"blockedBy\":{\"nodes\":[{\"number\":2,\"title\":\"caf\\xe9\"}],"
      "\"totalCount\":1}}')\n"
      "elif mode == 'repo-malformed':\n"
      "  require(repo)\n"
      "  sys.stdout.buffer.write(b'{bad')\n"
      "elif mode == 'dependency-malformed':\n"
      "  require(dependency)\n"
      "  sys.stdout.buffer.write(b'{bad')\n"
      "else:\n"
      "  sys.stderr.write('unexpected fake mode\\n')\n"
      "  raise SystemExit(92)\n",
      encoding="utf-8",
    )
    if os.name == "nt":
      launcher = bindir / "gh.cmd"
      launcher.write_text(
        f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n',
        encoding="utf-8",
      )
    else:
      launcher = bindir / "gh"
      launcher.write_text(
        f"#!{sys.executable}\n"
        f"exec(open({str(script)!r}, encoding='utf-8').read())\n",
        encoding="utf-8",
      )
      launcher.chmod(0o755)
    return bindir, log

  def environment(self, bindir: Path, log: Path, mode: str) -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = str(bindir)
    env["P11_LOG"] = str(log)
    env["P11_MODE"] = mode
    env["PYTHONUTF8"] = "0"
    env["PYTHONCOERCECLOCALE"] = "0"
    if os.name != "nt":
      env["LC_ALL"] = "C"
      env["LANG"] = "C"
    env.pop("GH_TOKEN", None)
    env.pop("GITHUB_TOKEN", None)
    return env

  def run_provider(
    self,
    executable: Path,
    arguments: list[str],
    env: dict[str, str],
    cwd: Path | None = None,
  ) -> subprocess.CompletedProcess:
    return subprocess.run(
      [sys.executable, str(executable), *arguments],
      capture_output=True,
      cwd=cwd,
      env=env,
    )

  def read_log(self, log: Path) -> list[list[str]]:
    return [
      json.loads(line)
      for line in log.read_text(encoding="utf-8").splitlines()
    ]

  def test_repo_info_decodes_utf8_under_restricted_locale(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      bindir, log = self.fake_gh(root)
      result = self.run_provider(
        REPO_INFO,
        ["--repository", "o/r", "issue", "get", "64"],
        self.environment(bindir, log, "repo-unicode"),
      )
      self.assertEqual(result.returncode, 0, result.stderr)
      value = json.loads(result.stdout.decode("utf-8"))
      self.assertEqual(value["title"], "München → 東京")
      self.assertEqual(self.read_log(log), [[
        "issue", "view", "64", "--json", "number,title,state,url",
        "--repo", "o/r",
      ]])

  def test_unicode_nonzero_diagnostic_is_controlled_for_both_executables(self):
    cases = (
      (
        REPO_INFO,
        ["--repository", "o/r", "issue", "get", "64"],
        "repo-error",
        "GitHub repo-info operation failed",
      ),
      (
        DEPENDENCIES,
        ["dependency", "get", "64"],
        "dependency-error",
        "GitHub dependency operation failed",
      ),
    )
    for executable, arguments, mode, diagnostic in cases:
      with self.subTest(executable=executable.name), tempfile.TemporaryDirectory() as td:
        root = Path(td)
        bindir, log = self.fake_gh(root)
        result = self.run_provider(
          executable,
          arguments,
          self.environment(bindir, log, mode),
        )
        error = result.stderr.decode("utf-8")
        self.assertEqual(result.returncode, 2, error)
        self.assertIn(diagnostic, error)
        self.assertIn("provider café → 東京", error)
        self.assertNotIn("Traceback", error)

  def test_cp1252_provider_bytes_fail_closed_without_traceback(self):
    cases = (
      (
        REPO_INFO,
        ["--repository", "o/r", "issue", "get", "64"],
        "repo-cp1252",
        "GitHub repo-info",
      ),
      (
        DEPENDENCIES,
        ["dependency", "get", "64"],
        "dependency-cp1252",
        "GitHub dependency",
      ),
    )
    for executable, arguments, mode, label in cases:
      with self.subTest(executable=executable.name), tempfile.TemporaryDirectory() as td:
        root = Path(td)
        bindir, log = self.fake_gh(root)
        result = self.run_provider(
          executable,
          arguments,
          self.environment(bindir, log, mode),
        )
        error = result.stderr.decode("utf-8")
        self.assertEqual(result.returncode, 2, error)
        self.assertIn(label, error)
        self.assertIn("not valid UTF-8", error)
        self.assertNotIn("Traceback", error)

  def test_missing_gh_is_controlled_for_both_executables(self):
    cases = (
      (REPO_INFO, ["--repository", "o/r", "issue", "get", "64"]),
      (DEPENDENCIES, ["dependency", "get", "64"]),
    )
    for executable, arguments in cases:
      with self.subTest(executable=executable.name), tempfile.TemporaryDirectory() as td:
        root = Path(td)
        env = dict(os.environ)
        env["PATH"] = str(root)
        env.pop("GH_TOKEN", None)
        env.pop("GITHUB_TOKEN", None)
        result = self.run_provider(executable, arguments, env)
        error = result.stderr.decode("utf-8")
        self.assertEqual(result.returncode, 2, error)
        self.assertIn("operation failed", error)
        self.assertNotIn("Traceback", error)

  def test_malformed_provider_json_fails_closed(self):
    cases = (
      (
        REPO_INFO,
        ["--repository", "o/r", "issue", "get", "64"],
        "repo-malformed",
        "GitHub issue response is malformed",
      ),
      (
        DEPENDENCIES,
        ["dependency", "get", "64"],
        "dependency-malformed",
        "GitHub dependency response is malformed",
      ),
    )
    for executable, arguments, mode, diagnostic in cases:
      with self.subTest(executable=executable.name), tempfile.TemporaryDirectory() as td:
        root = Path(td)
        bindir, log = self.fake_gh(root)
        result = self.run_provider(
          executable,
          arguments,
          self.environment(bindir, log, mode),
        )
        error = result.stderr.decode("utf-8")
        self.assertEqual(result.returncode, 2, error)
        self.assertIn(diagnostic, error)
        self.assertNotIn("Traceback", error)

  def test_dependency_related_uses_exact_provider_route_without_fallback(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      bindir, log = self.fake_gh(root)
      result = self.run_provider(
        DEPENDENCIES,
        ["dependency", "related", "64"],
        self.environment(bindir, log, "dependency-related"),
      )
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(json.loads(result.stdout.decode("utf-8")), {
        "schema_version": 1,
        "issue": 64,
        "dependencies": [2],
        "dependants": [70],
      })
      self.assertEqual(self.read_log(log), [[
        "issue", "view", "64", "--json", "blockedBy,blocking",
      ]])


if __name__ == "__main__":
  unittest.main()
