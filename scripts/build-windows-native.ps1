[CmdletBinding()]
param(
    [switch]$Register,
    [string]$AppName = "pxl",
    [string]$DisplayName = "Pxl",
    [string]$Version = "0.1.0",
    [string]$UvVersion = "0.11.19",
    [string]$UvTarget = "",
    [string]$DistDir = "",
    [string]$BuildDir = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$LauncherPath = Join-Path $RepoRoot "src\windows\launcher.c"
$ScriptPath = Join-Path $RepoRoot "pxl.py"
$IconPath = Join-Path $RepoRoot "assets\pxl.ico"

if ([string]::IsNullOrWhiteSpace($DistDir)) {
    $DistDir = Join-Path $RepoRoot "dist\pxl"
}

if ([string]::IsNullOrWhiteSpace($BuildDir)) {
    $BuildDir = Join-Path $RepoRoot "build\windows-native"
}

$ExePath = Join-Path $DistDir "$AppName.exe"
$RcPath = Join-Path $BuildDir "$AppName.rc"
$ResPath = Join-Path $BuildDir "$AppName.res"

function Assert-File {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required file not found: $Path"
    }
}

function Find-Tool {
    param([string[]]$Names)

    foreach ($Name in $Names) {
        $Command = Get-Command $Name -ErrorAction SilentlyContinue
        if ($null -ne $Command) {
            return $Command.Source
        }
    }

    return $null
}

function Get-DefaultUvTarget {
    $Architecture = $env:PROCESSOR_ARCHITECTURE
    if ([string]::IsNullOrWhiteSpace($Architecture)) {
        $Architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    }

    switch -Regex ($Architecture) {
        "ARM64|Arm64" { return "aarch64-pc-windows-msvc" }
        default { return "x86_64-pc-windows-msvc" }
    }
}

function Convert-VersionForResource {
    param([string]$Value)

    $Parts = @($Value -split "[^0-9]+" | Where-Object { $_ -ne "" })
    while ($Parts.Count -lt 4) {
        $Parts += "0"
    }
    return ($Parts[0..3] -join ",")
}

function Escape-RcString {
    param([string]$Value)

    return $Value.Replace("\", "\\").Replace('"', '\"')
}

function Write-ResourceFile {
    $EscapedIconPath = Escape-RcString ([System.IO.Path]::GetFullPath($IconPath))
    $FileVersion = Convert-VersionForResource $Version
    $ProductVersion = $FileVersion
    $EscapedVersion = Escape-RcString $Version
    $EscapedDisplayName = Escape-RcString $DisplayName
    $EscapedAppName = Escape-RcString $AppName

    $Content = @"
#include <windows.h>

1 ICON "$EscapedIconPath"

1 VERSIONINFO
FILEVERSION $FileVersion
PRODUCTVERSION $ProductVersion
FILEFLAGSMASK 0x3fL
FILEFLAGS 0x0L
FILEOS 0x40004L
FILETYPE 0x1L
FILESUBTYPE 0x0L
BEGIN
    BLOCK "StringFileInfo"
    BEGIN
        BLOCK "040904b0"
        BEGIN
            VALUE "CompanyName", "pxl"
            VALUE "FileDescription", "$EscapedDisplayName image viewer launcher"
            VALUE "FileVersion", "$EscapedVersion"
            VALUE "InternalName", "$EscapedAppName"
            VALUE "OriginalFilename", "$EscapedAppName.exe"
            VALUE "ProductName", "$EscapedDisplayName"
            VALUE "ProductVersion", "$EscapedVersion"
        END
    END
    BLOCK "VarFileInfo"
    BEGIN
        VALUE "Translation", 0x0409, 1200
    END
END
"@

    Set-Content -LiteralPath $RcPath -Value $Content -Encoding ASCII
}

function Invoke-NativeBuild {
    $Compiler = Find-Tool @("cl.exe", "clang-cl.exe")
    if ($null -eq $Compiler) {
        throw "Could not find cl.exe or clang-cl.exe. Run this from a Visual Studio Developer PowerShell, or install Visual Studio Build Tools/LLVM."
    }

    $ResourceCompiler = Find-Tool @("rc.exe", "llvm-rc.exe")
    if ($null -eq $ResourceCompiler) {
        throw "Could not find rc.exe or llvm-rc.exe. Install the Windows SDK or LLVM resource compiler."
    }

    & $ResourceCompiler /nologo "/fo$ResPath" $RcPath
    if ($LASTEXITCODE -ne 0) {
        throw "Resource compilation failed with exit code $LASTEXITCODE."
    }

    $CompileArgs = @(
        "/nologo",
        "/O2",
        "/W4",
        "/DUNICODE",
        "/D_UNICODE",
        "/DWIN32_LEAN_AND_MEAN",
        "/Fe:$ExePath",
        $LauncherPath,
        $ResPath,
        "/link",
        "/SUBSYSTEM:WINDOWS",
        "user32.lib",
        "shell32.lib"
    )

    Push-Location $BuildDir
    try {
        & $Compiler @CompileArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Native Windows launcher build failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}

function Download-Uv {
    param([string]$Destination)

    if ([string]::IsNullOrWhiteSpace($UvTarget)) {
        $UvTarget = Get-DefaultUvTarget
    }

    $ArchiveName = "uv-$UvTarget.zip"
    $Url = "https://github.com/astral-sh/uv/releases/download/$UvVersion/$ArchiveName"
    $ArchivePath = Join-Path $BuildDir $ArchiveName
    $ExtractDir = Join-Path $BuildDir "uv"

    Remove-Item -LiteralPath $ExtractDir -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $ExtractDir -Force | Out-Null

    Write-Host "Downloading $Url"
    Invoke-WebRequest -Uri $Url -OutFile $ArchivePath
    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $ExtractDir -Force

    $UvExe = Get-ChildItem -LiteralPath $ExtractDir -Recurse -Filter "uv.exe" |
        Select-Object -First 1
    if ($null -eq $UvExe) {
        throw "uv.exe was not found in $ArchiveName."
    }

    Copy-Item -LiteralPath $UvExe.FullName -Destination $Destination -Force
}

Assert-File $LauncherPath
Assert-File $ScriptPath

& (Join-Path $PSScriptRoot "create-windows-icon.ps1") -Path $IconPath
Assert-File $IconPath

Remove-Item -LiteralPath $DistDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null

Write-ResourceFile
Invoke-NativeBuild

Copy-Item -LiteralPath $ScriptPath -Destination (Join-Path $DistDir "pxl.py") -Force
Download-Uv -Destination (Join-Path $DistDir "uv.exe")

$DistAssetsDir = Join-Path $DistDir "assets"
New-Item -ItemType Directory -Path $DistAssetsDir -Force | Out-Null
Copy-Item -LiteralPath $IconPath -Destination (Join-Path $DistAssetsDir "pxl.ico") -Force

Write-Host "Built $ExePath"
Write-Host "Bundled $(Join-Path $DistDir 'uv.exe')"

if ($Register) {
    & (Join-Path $PSScriptRoot "register-windows.ps1") -ExePath $ExePath
}
