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

  return certify_stages(
    source_sha=source_sha,parent_sha=parent_sha,
    read_stage=reader,read_mit_policy=read_mit_policy)
