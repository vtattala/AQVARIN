$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$checkout = Join-Path $workspace 'third_party/drowning-detection'
$revision = 'b75850a26cc8e6b255bd09ffb26c333adce4fa2a'
if (!(Test-Path -LiteralPath $checkout)) {
    git clone https://github.com/Z5cc/drowning-detection.git $checkout
    if ($LASTEXITCODE -ne 0) { throw 'Repository clone failed' }
}
git -C $checkout checkout --detach $revision
if ($LASTEXITCODE -ne 0) { throw 'Pinned repository checkout failed' }
Write-Output 'Optional Z5cc source ready. Its trained temporal checkpoint is still required. The default three-class YOLO model is installed by scripts/setup_action_models.py.'
