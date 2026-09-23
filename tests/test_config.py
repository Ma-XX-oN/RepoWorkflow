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


if __name__ == "__main__":
  unittest.main()
