[CmdletBinding()]
param(
    [switch]$Register
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$LauncherPath = Join-Path $RepoRoot "scripts\windows_launcher.py"
$ScriptPath = Join-Path $RepoRoot "pxl.py"
$IconPath = Join-Path $RepoRoot "assets\pxl.ico"
$DistDir = Join-Path $RepoRoot "dist\pxl"
$BuildDir = Join-Path $RepoRoot "build\pyinstaller"
$ExePath = Join-Path $DistDir "pxl.exe"

if (-not (Test-Path -LiteralPath $ScriptPath)) {
    throw "Could not find pxl.py at $ScriptPath"
}

if (-not (Test-Path -LiteralPath $LauncherPath)) {
    throw "Could not find the Windows launcher at $LauncherPath"
}

$UvCommand = Get-Command uv -ErrorAction SilentlyContinue
if ($null -eq $UvCommand) {
    throw "uv was not found on PATH."
}

& (Join-Path $PSScriptRoot "create-windows-icon.ps1") -Path $IconPath

New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null

$PyInstallerArgs = @(
    "run",
    "--with",
    "pyinstaller",
    "pyinstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--name",
    "pxl",
    "--icon",
    $IconPath,
    "--distpath",
    $DistDir,
    "--workpath",
    $BuildDir,
    "--specpath",
    $BuildDir,
    $LauncherPath
)

Push-Location $RepoRoot
try {
    & $UvCommand.Source @PyInstallerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

Copy-Item -LiteralPath $ScriptPath -Destination (Join-Path $DistDir "pxl.py") -Force

$DistAssetsDir = Join-Path $DistDir "assets"
New-Item -ItemType Directory -Path $DistAssetsDir -Force | Out-Null
Copy-Item -LiteralPath $IconPath -Destination (Join-Path $DistAssetsDir "pxl.ico") -Force

Write-Host "Built $ExePath"

if ($Register) {
    & (Join-Path $PSScriptRoot "register-windows.ps1") -ExePath $ExePath
}
