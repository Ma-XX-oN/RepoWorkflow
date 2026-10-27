from pathlib import Path
import json
import tempfile
import unittest

from repo_workflow.config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
  def write(self, root: Path, value: dict) -> None:
    (root / ".ci").mkdir()
    (root / ".ci" / "repoworkflow.json").write_text(json.dumps(value))

  def base(self) -> dict:
    return {
      "schema": 1,
      "versionCommand": ["python", "version.py"],
      "repository": {"integrationBranch": "main", "authoritativeRemote": "origin"},
      "environments": [{
        "id": "one", "validationCommand": ["python", "validate.py"]
      }],
      "artifacts": [],
    }

  def test_valid_config_normalizes_defaults(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      self.write(root, self.base())
      config = load_config(root)
      self.assertTrue(config["environments"][0]["required"])
      self.assertEqual(config["environments"][0]["platform"], "any")

  def test_info_command_is_validated_when_configured(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      value = self.base()
      value["infoCommand"] = ["python", "repo-info.py"]
      self.write(root, value)
      self.assertEqual(load_config(root)["infoCommand"], value["infoCommand"])
      value["infoCommand"] = []
      (root / ".ci" / "repoworkflow.json").write_text(json.dumps(value))
      with self.assertRaisesRegex(ConfigError, "infoCommand"):
        load_config(root)

  def test_obsolete_set_version_command_is_rejected(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      value = self.base()
      value["setVersionCommand"] = ["python", "version.py", "--set"]
      self.write(root, value)
      with self.assertRaisesRegex(ConfigError, "unsupported fields"):
        load_config(root)

  def test_duplicate_environment_is_rejected(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      value = self.base()
      value["environments"].append(dict(value["environments"][0]))
      self.write(root, value)
      with self.assertRaises(ConfigError):
        load_config(root)

  def test_duplicate_artifact_output_is_rejected(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      value = self.base()
      artifact = {
        "id": "a", "generatorCommand": ["gen"], "verifierCommand": ["verify"],
        "outputs": ["dist/out.js"]
      }
      value["artifacts"] = [artifact, {**artifact, "id": "b"}]
      self.write(root, value)
      with self.assertRaises(ConfigError):
        load_config(root)

  def test_artifact_verifier_must_be_independent_command(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      value = self.base()
      value["artifacts"] = [{
        "id": "bundle",
        "generatorCommand": ["python", "scripts/artifact.py"],
        "verifierCommand": ["python", "scripts/artifact.py"],
        "outputs": ["dist/out.js"],
      }]
      self.write(root, value)
      with self.assertRaisesRegex(ConfigError, "independent verifier"):
        load_config(root)

  def test_non_committed_artifact_declaration_is_rejected(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      value = self.base()
      value["artifacts"] = [{
        "id": "bundle",
        "generatorCommand": ["gen"],
        "verifierCommand": ["verify"],
        "outputs": ["dist/out.js"],
        "committed": False,
      }]
      self.write(root, value)
      with self.assertRaisesRegex(ConfigError, "committed generated artifacts"):
        load_config(root)

  def test_unknown_fields_are_rejected(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      value = self.base()
      value["magic"] = True
      self.write(root, value)
      with self.assertRaises(ConfigError):
        load_config(root)


  def _artifact(self, artifact_id: str, outputs: list[str]) -> dict:
    return {
      "id": artifact_id, "generatorCommand": ["gen"],
      "verifierCommand": ["verify"], "outputs": outputs,
    }

  def test_canonical_slash_outputs_preserve_identity(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      value = self.base()
      names = ["dist/out.js", "dir with spaces/été 日本語.js", "data/v1/file.txt"]
      value["artifacts"] = [self._artifact("bundle", names)]
      self.write(root, value)
      self.assertEqual(load_config(root)["artifacts"][0]["outputs"], names)

  def test_noncanonical_output_spellings_are_rejected(self):
    invalid = [
      "", "/dist/out.js", "//server/share", "C:/dist/out.js",
      "C:\\\\dist\\\\out.js", "dist" + chr(92) + "out.js", "dist/" + chr(92) + "out.js",
      "../dist/out.js", "dist/../out.js", "dist/./out.js",
      "./dist/out.js", "dist//out.js", "dist/out.js/",
      ".", "..", "dist/.", "dist/..", "dist/" + chr(0) + "out.js",
    ]
    for name in invalid:
      with self.subTest(name=repr(name)), tempfile.TemporaryDirectory() as td:
        root = Path(td)
        value = self.base()
        value["artifacts"] = [self._artifact("bundle", [name])]
        self.write(root, value)
        # The pre-existing non-empty-string field validator owns empty names.
        if name == "":
          with self.assertRaises(ConfigError):
            load_config(root)
        else:
          with self.assertRaisesRegex(ConfigError, "canonical repository-relative"):
            load_config(root)

  def test_backslash_cannot_alias_slash_output(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      value = self.base()
      value["artifacts"] = [
        self._artifact("slash", ["dist/out.js"]),
        self._artifact("backslash", ["dist" + chr(92) + "out.js"]),
      ]
      self.write(root, value)
      with self.assertRaisesRegex(ConfigError, "canonical repository-relative"):
        load_config(root)

  def test_duplicate_same_artifact_output_is_rejected(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      value = self.base()
      value["artifacts"] = [
        self._artifact("bundle", ["dist/out.js", "dist/out.js"]),
      ]
      self.write(root, value)
      with self.assertRaisesRegex(ConfigError, "declared by both"):
        load_config(root)

  def test_canonical_repository_path_public_contract(self):
    from repo_workflow.config import canonical_repository_path
    self.assertEqual(
      canonical_repository_path("a folder/文書.txt"), "a folder/文書.txt"
    )
    with self.assertRaises(ConfigError):
      canonical_repository_path("a" + chr(92) + "folder.txt")


if __name__ == "__main__":
  unittest.main()
