"""Stage orchestration: hosted ART/AIT plus independent release/MIT.

No stage issuer is invented. Provider readers must be authenticated by the
host application. This boundary never claims to be a release/MIT provider.
"""
from .done_stage_hosted import verified_hosted_automatic_stage
from .done_stage_certification import certify_stages, StageCertificationError


def certify_provider_stages(
    *, repository, source_sha, parent_sha,
    read_hosted_record, read_hosted_binding, verify_hosted_artifact,
    read_release_stage, read_mit_stage, read_mit_policy):
  """Reconcile separately authenticated automatic and manual stage oracles."""
  required=(
    read_hosted_record,read_hosted_binding,verify_hosted_artifact,
    read_release_stage,read_mit_stage,read_mit_policy,
  )
  if (type(repository) is not str or not repository.strip()
      or any(not callable(fn) for fn in required)):
    raise StageCertificationError(
      "hosted ART/AIT and distinct release/MIT provider authorities required")

  def reader(stage, tested_sha, base_sha):
    if stage in {"ART","AIT"}:
      return verified_hosted_automatic_stage(
        repository=repository,stage=stage,
        tested_sha=tested_sha,expected_parent_sha=base_sha,
        read_record=read_hosted_record,
        read_binding=read_hosted_binding,
        verify_artifact=verify_hosted_artifact)
    if stage=="release":
      return read_release_stage(tested_sha,base_sha)
    if stage=="MIT":
      return read_mit_stage(tested_sha,base_sha)
    raise StageCertificationError("unknown stage issuer")

  certified=certify_stages(
    source_sha=source_sha,parent_sha=parent_sha,
    read_stage=reader,read_mit_policy=read_mit_policy)
  # Release and manual permission can be withdrawn while the hosted ART/AIT
  # receipts are checked. Read their separate issuers again before returning.
  try:
    current_policy=read_mit_policy(source_sha,parent_sha)
    current_release=read_release_stage(source_sha,parent_sha)
    current_mit=(read_mit_stage(source_sha,parent_sha)
                 if certified.mit_policy.required else None)
  except Exception as error:
    raise StageCertificationError(
      "post-certification stage authority UNKNOWN") from error
  authoritative={s.stage:s for s in certified.stages}
  if (current_policy!=certified.mit_policy
      or current_release!=authoritative["release"]
      or (certified.mit_policy.required
          and current_mit!=authoritative["MIT"])):
    raise StageCertificationError(
      "stage authority changed during certification")
  return certified


def certify_github_app_stages(
    *, repository, source_sha, parent_sha,
    read_hosted_record, read_hosted_binding, verify_hosted_artifact,
    release_binding, release_app_id, mit_binding, mit_app_id,
    read_mit_policy, read_check=None):
  """Compose hosted ART/AIT with a separately trusted GitHub App issuer.

  Absence of an actual release check or a required MIT check is a failure,
  never an automatic waiver or inference from the hosted regression suite.
  """
  from .done_check_issuer import (
    CheckIssuerBinding,bind_github_check_oracle,read_github_check,
  )
  if (not isinstance(release_binding,CheckIssuerBinding)
      or release_binding.stage!="release"
      or release_binding.repository!=repository
      or release_binding.source_sha!=source_sha
      or release_binding.parent_sha!=parent_sha):
    raise StageCertificationError(
      "current independent release issuer is unconfigured")
  reader=read_github_check if read_check is None else read_check
  release=bind_github_check_oracle(
    binding=release_binding,trusted_app_id=release_app_id,
    read_check=reader)
  if mit_binding is None:
    def mit(source,parent):
      raise StageCertificationError(
        "independent manual tester issuer is unconfigured")
  else:
    if (not isinstance(mit_binding,CheckIssuerBinding)
        or mit_binding.stage!="MIT"
        or mit_binding.repository!=repository
        or mit_binding.source_sha!=source_sha
        or mit_binding.parent_sha!=parent_sha):
      raise StageCertificationError(
        "current independent manual tester issuer invalid")
    mit=bind_github_check_oracle(
      binding=mit_binding,trusted_app_id=mit_app_id,read_check=reader)
  return certify_provider_stages(
    repository=repository,source_sha=source_sha,parent_sha=parent_sha,
    read_hosted_record=read_hosted_record,
    read_hosted_binding=read_hosted_binding,
    verify_hosted_artifact=verify_hosted_artifact,
    read_release_stage=release,read_mit_stage=mit,
    read_mit_policy=read_mit_policy)
