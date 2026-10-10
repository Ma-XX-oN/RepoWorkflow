from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = ROOT / ".github" / "workflows" / "consumer-ci.yml"


class TemplateTests(unittest.TestCase):
  def test_github_adapter_is_product_agnostic_and_calls_shared_engine(self):
    text = IMPLEMENTATION.read_text()
    for product in (
      "AIConversationCore", "AgentPanelSpeaker", "DownloadConversation",
      "AI-General-Memory", "Multi-AI",
    ):
      self.assertNotIn(product, text)
    for command in (
      "repository-policy", "branch-policy", "preflight",
      "materialize-artifacts", "finalize", "stable-preflight",
      "stable-finalize", "repo_ci_github_machine.py mode",
      "repo_ci_github_machine.py matrix",
      "repo_ci_github_machine.py prepare-context",
      '"repo-ci", "execute"',
    ):
      self.assertIn(command, text)
    provider = (ROOT / "repo_workflow" / "repo_ci_github_provider.py").read_text()
    self.assertIn('"stable-run" if inputs["mode"] == "stable" else "run"', provider)
    self.assertIn("submodules: recursive", text)
    self.assertIn("fetch-depth: 0", text)

  def test_only_prepare_and_finalize_have_write_permission(self):
    text = IMPLEMENTATION.read_text()
    self.assertEqual(text.count("contents: write"), 2)
    self.assertIn("permissions:\n  contents: read", text)

  def test_github_event_path_is_shell_expanded(self):
    text = IMPLEMENTATION.read_text(encoding="utf-8")
    self.assertIn('--event-path "$GITHUB_EVENT_PATH"', text)
    self.assertNotIn("--event-path '$GITHUB_EVENT_PATH'", text)

  def test_matrix_result_filenames_are_unique_per_environment(self):
    text = IMPLEMENTATION.read_text()
    self.assertIn(
      '${{ runner.temp }}/repoworkflow-result/${{ matrix.id }}.json',
      text,
    )
    self.assertNotIn(
      '${{ runner.temp }}/repoworkflow-result/result.json',
      text,
    )

  def test_artifact_gate_result_is_uploaded_for_finalization(self):
    text = IMPLEMENTATION.read_text()
    self.assertIn("repoworkflow-result-artifacts", text)
    self.assertIn("artifacts.json", text)
    self.assertIn("continue-on-error: true", text)

  def test_missing_result_artifacts_reach_shared_finalizer(self):
    text = IMPLEMENTATION.read_text()
    self.assertIn("name: Prepare result collection directory", text)
    self.assertRegex(
      text,
      r"uses: actions/download-artifact@v4\n\s+continue-on-error: true",
    )

  def test_expensive_jobs_are_authoritative_mode_gated(self):
    text = IMPLEMENTATION.read_text()
    self.assertIn("needs.policy.outputs.mode != 'none'", text)
    self.assertNotIn("needs.policy.outputs.run_ci == 'true'", text)
    self.assertIn("fail-fast: false", text)


if __name__ == "__main__":
  unittest.main()
