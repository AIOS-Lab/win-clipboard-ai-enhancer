param(
    [string]$OutputRoot = "",
    [string]$ReleaseDirName = "portable_release"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$buildRoot = Join-Path $repoRoot ".portable_build"
$distDir = Join-Path $buildRoot "dist"
$workDir = Join-Path $buildRoot "build"
$specDir = $buildRoot
$entryScript = Join-Path $repoRoot "src\\main.py"

if (Test-Path $buildRoot) {
    Remove-Item -Recurse -Force $buildRoot
}

New-Item -ItemType Directory -Force -Path $distDir, $workDir, $specDir | Out-Null

& pyinstaller --noconfirm --clean --onefile --windowed `
    --name "WinClipboardAIEnhancerPortable" `
    --distpath $distDir `
    --workpath $workDir `
    --specpath $specDir `
    $entryScript

if ($OutputRoot) {
    $releaseDir = Join-Path $OutputRoot $ReleaseDirName
    $targetExe = Join-Path $releaseDir "WinClipboardAIEnhancerPortable.exe"
    New-Item -ItemType Directory -Force -Path $releaseDir, (Join-Path $releaseDir "data") | Out-Null
    Copy-Item -Force -Path (Join-Path $distDir "WinClipboardAIEnhancerPortable.exe") -Destination $targetExe
}
