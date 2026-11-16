# Dot-source this file to prepend manual-test progress to the existing prompt.
# Repeated installation preserves the original prompt rather than nesting hooks.
if (-not (Test-Path Variable:global:RwfOriginalPrompt)) {
  $global:RwfOriginalPrompt = $function:prompt
}
$global:RwfPromptEngine = Join-Path (Split-Path $PSScriptRoot -Parent) 'repo_workflow.py'
function global:prompt {
  $rwfSavedExit = $global:LASTEXITCODE
  try {
    $rwfPrefix = & python $global:RwfPromptEngine --root (Get-Location).Path manual-prompt 2>$null
    if ($LASTEXITCODE -eq 0 -and $rwfPrefix -match '^\[MIT [0-9]+/[0-9]+\]$') {
      Write-Host "$rwfPrefix " -NoNewline
    }
  } finally {
    $global:LASTEXITCODE = $rwfSavedExit
  }
  & $global:RwfOriginalPrompt
}
