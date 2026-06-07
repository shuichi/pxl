[CmdletBinding()]
param(
    [string]$Path
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Path)) {
    $RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
    $Path = Join-Path $RepoRoot "assets\pxl.ico"
}

$TargetPath = [System.IO.Path]::GetFullPath($Path)
$TargetDir = [System.IO.Path]::GetDirectoryName($TargetPath)
[System.IO.Directory]::CreateDirectory($TargetDir) | Out-Null

Add-Type -AssemblyName System.Drawing

function New-Brush {
    param([string]$Color)

    return [System.Drawing.SolidBrush]::new(
        [System.Drawing.ColorTranslator]::FromHtml($Color)
    )
}

function Add-RoundedRectangle {
    param(
        [System.Drawing.Drawing2D.GraphicsPath]$Path,
        [float]$X,
        [float]$Y,
        [float]$Width,
        [float]$Height,
        [float]$Radius
    )

    $Diameter = $Radius * 2
    $Path.AddArc($X, $Y, $Diameter, $Diameter, 180, 90)
    $Path.AddArc($X + $Width - $Diameter, $Y, $Diameter, $Diameter, 270, 90)
    $Path.AddArc($X + $Width - $Diameter, $Y + $Height - $Diameter, $Diameter, $Diameter, 0, 90)
    $Path.AddArc($X, $Y + $Height - $Diameter, $Diameter, $Diameter, 90, 90)
    $Path.CloseFigure()
}

function New-IconBitmap {
    param([int]$Size)

    $Bitmap = [System.Drawing.Bitmap]::new(
        $Size,
        $Size,
        [System.Drawing.Imaging.PixelFormat]::Format32bppArgb
    )
    $Graphics = [System.Drawing.Graphics]::FromImage($Bitmap)

    try {
        $Graphics.Clear([System.Drawing.Color]::Transparent)
        $Graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $Graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality

        $BaseInset = [Math]::Max(1, [int]($Size * 0.035))
        $BaseRadius = [Math]::Max(3, [int]($Size * 0.18))
        $BasePath = [System.Drawing.Drawing2D.GraphicsPath]::new()
        Add-RoundedRectangle $BasePath $BaseInset $BaseInset ($Size - ($BaseInset * 2)) ($Size - ($BaseInset * 2)) $BaseRadius

        $BaseBrush = New-Brush "#10131d"
        $Graphics.FillPath($BaseBrush, $BasePath)
        $BaseBrush.Dispose()

        $HighlightBrush = [System.Drawing.SolidBrush]::new(
            [System.Drawing.Color]::FromArgb(42, 255, 255, 255)
        )
        $Graphics.FillRectangle(
            $HighlightBrush,
            [int]($Size * 0.11),
            [int]($Size * 0.10),
            [int]($Size * 0.78),
            [Math]::Max(1, [int]($Size * 0.025))
        )
        $HighlightBrush.Dispose()

        $BasePath.Dispose()
        $Graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::None
        $Graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half

        $Palette = @{
            A = "#00d1ff"
            B = "#3b82f6"
            C = "#6366f1"
            D = "#a855f7"
            E = "#ec4899"
            F = "#f43f5e"
            G = "#f97316"
            H = "#facc15"
            I = "#84cc16"
            J = "#22c55e"
            K = "#14b8a6"
            L = "#f8fafc"
            M = "#38bdf8"
            N = "#fb7185"
        }

        $Pixels = @(
            "AABCDEF G".Replace(" ", ""),
            "KABCDEGH",
            "KABLLDGH",
            "JKAHHDEG",
            "IJKBCDEF",
            "HIJKBCDE",
            "GHIJKABC",
            "NGHIJKAB"
        )

        $GridSize = 8
        $Gap = [Math]::Max(0, [int]($Size / 42))
        $Cell = [Math]::Max(1, [int][Math]::Floor(($Size * 0.72 - ($Gap * ($GridSize - 1))) / $GridSize))
        $GridPixels = ($Cell * $GridSize) + ($Gap * ($GridSize - 1))
        $Start = [int][Math]::Floor(($Size - $GridPixels) / 2)

        for ($Y = 0; $Y -lt $GridSize; $Y++) {
            for ($X = 0; $X -lt $GridSize; $X++) {
                $Key = $Pixels[$Y][$X].ToString()
                $Brush = New-Brush $Palette[$Key]
                $Graphics.FillRectangle(
                    $Brush,
                    $Start + ($X * ($Cell + $Gap)),
                    $Start + ($Y * ($Cell + $Gap)),
                    $Cell,
                    $Cell
                )
                $Brush.Dispose()
            }
        }

        $ShadowBrush = [System.Drawing.SolidBrush]::new(
            [System.Drawing.Color]::FromArgb(72, 0, 0, 0)
        )
        $Graphics.FillRectangle(
            $ShadowBrush,
            $Start,
            $Start + $GridPixels - [Math]::Max(1, [int]($Size * 0.018)),
            $GridPixels,
            [Math]::Max(1, [int]($Size * 0.018))
        )
        $ShadowBrush.Dispose()

        return $Bitmap
    }
    catch {
        $Bitmap.Dispose()
        throw
    }
    finally {
        $Graphics.Dispose()
    }
}

function Convert-BitmapToPngBytes {
    param([System.Drawing.Bitmap]$Bitmap)

    $Memory = [System.IO.MemoryStream]::new()
    try {
        $Bitmap.Save($Memory, [System.Drawing.Imaging.ImageFormat]::Png)
        return [byte[]]$Memory.ToArray()
    }
    finally {
        $Memory.Dispose()
    }
}

$Entries = @()
foreach ($Size in @(256, 128, 64, 48, 32, 16)) {
    $Bitmap = New-IconBitmap $Size
    try {
        $Data = Convert-BitmapToPngBytes $Bitmap
        $Entries += [PSCustomObject]@{
            Size = $Size
            Data = $Data
        }
    }
    finally {
        $Bitmap.Dispose()
    }
}

$Stream = [System.IO.File]::Create($TargetPath)
$Writer = [System.IO.BinaryWriter]::new($Stream)

try {
    $Writer.Write([UInt16]0)
    $Writer.Write([UInt16]1)
    $Writer.Write([UInt16]$Entries.Count)

    $Offset = 6 + (16 * $Entries.Count)
    foreach ($Entry in $Entries) {
        $Writer.Write([byte]$(if ($Entry.Size -eq 256) { 0 } else { $Entry.Size }))
        $Writer.Write([byte]$(if ($Entry.Size -eq 256) { 0 } else { $Entry.Size }))
        $Writer.Write([byte]0)
        $Writer.Write([byte]0)
        $Writer.Write([UInt16]1)
        $Writer.Write([UInt16]32)
        $Writer.Write([UInt32]$Entry.Data.Length)
        $Writer.Write([UInt32]$Offset)
        $Offset += $Entry.Data.Length
    }

    foreach ($Entry in $Entries) {
        $Writer.Write([byte[]]$Entry.Data)
    }
}
finally {
    $Writer.Dispose()
    $Stream.Dispose()
}

Write-Host "Wrote $TargetPath"
