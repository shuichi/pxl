[CmdletBinding()]
param(
    [switch]$Register
)

$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "build-windows-native.ps1") -Register:$Register
