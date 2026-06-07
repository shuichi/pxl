[CmdletBinding()]
param(
    [string]$ExePath,
    [string[]]$Extensions = @(
        ".avif",
        ".bmp",
        ".dib",
        ".gif",
        ".ico",
        ".jfif",
        ".jpe",
        ".jpeg",
        ".jpg",
        ".png",
        ".tif",
        ".tiff",
        ".webp"
    )
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ExePath)) {
    $RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
    $ExePath = Join-Path $RepoRoot "dist\pxl\pxl.exe"
}

if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "Could not find pxl.exe at $ExePath. Run scripts\build-windows.ps1 first."
}

$ResolvedExePath = (Resolve-Path -LiteralPath $ExePath).Path
$ProgId = "pxl.Image"
$ApplicationKey = "Software\Classes\Applications\pxl.exe"
$Command = '"' + $ResolvedExePath + '" "%1"'
$Icon = '"' + $ResolvedExePath + '",0'

function New-RegistryKey {
    param([string]$SubKey)

    $Key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($SubKey)
    if ($null -eq $Key) {
        throw "Could not create HKCU:\$SubKey"
    }
    $Key.Dispose()
}

function Set-RegistryString {
    param(
        [string]$SubKey,
        [string]$Name,
        [string]$Value
    )

    $Key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($SubKey)
    if ($null -eq $Key) {
        throw "Could not create HKCU:\$SubKey"
    }
    try {
        $Key.SetValue($Name, $Value, [Microsoft.Win32.RegistryValueKind]::String)
    }
    finally {
        $Key.Dispose()
    }
}

function Set-RegistryNone {
    param(
        [string]$SubKey,
        [string]$Name
    )

    $Key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($SubKey)
    if ($null -eq $Key) {
        throw "Could not create HKCU:\$SubKey"
    }
    try {
        $Key.SetValue($Name, [byte[]]@(), [Microsoft.Win32.RegistryValueKind]::None)
    }
    finally {
        $Key.Dispose()
    }
}

Set-RegistryString "Software\Classes\$ProgId" "" "pxl image"
Set-RegistryString "Software\Classes\$ProgId\DefaultIcon" "" $Icon
Set-RegistryString "Software\Classes\$ProgId\shell\open\command" "" $Command

Set-RegistryString $ApplicationKey "FriendlyAppName" "pxl"
Set-RegistryString "$ApplicationKey\DefaultIcon" "" $Icon
Set-RegistryString "$ApplicationKey\shell\open\command" "" $Command
Set-RegistryString "$ApplicationKey\Capabilities" "ApplicationName" "pxl"
Set-RegistryString "$ApplicationKey\Capabilities" "ApplicationDescription" "Open images with pxl."

foreach ($Extension in $Extensions) {
    if (-not $Extension.StartsWith(".")) {
        $Extension = ".$Extension"
    }

    Set-RegistryString "$ApplicationKey\SupportedTypes" $Extension ""
    Set-RegistryString "$ApplicationKey\Capabilities\FileAssociations" $Extension $ProgId
    New-RegistryKey "Software\Classes\$Extension\OpenWithList\pxl.exe"
    Set-RegistryNone "Software\Classes\$Extension\OpenWithProgids" $ProgId
}

Set-RegistryString "Software\RegisteredApplications" "pxl" "$ApplicationKey\Capabilities"

if (-not ("Pxl.ShellNotify" -as [type])) {
    Add-Type -Namespace Pxl -Name ShellNotify -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("Shell32.dll")]
public static extern void SHChangeNotify(long wEventId, uint uFlags, System.IntPtr dwItem1, System.IntPtr dwItem2);
'@
}

[Pxl.ShellNotify]::SHChangeNotify(0x08000000, 0, [System.IntPtr]::Zero, [System.IntPtr]::Zero)

Write-Host "Registered $ResolvedExePath for image files."
Write-Host "Windows may still ask you to choose pxl once from 'Open with' or Default apps."
