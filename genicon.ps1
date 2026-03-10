# =========================
# iOS App Icon Generator
# From Segoe Fluent Icons
# =========================

Add-Type -AssemblyName System.Drawing

# ---- CONFIG ----
$Glyph        = [char]0xE700      # Change this to the Fluent Icon glyph you want
$FontName     = "Segoe Fluent Icons"
$Foreground   = [System.Drawing.Color]::White
$Background   = [System.Drawing.Color]::Transparent
$OutputDir    = ".\AppIcons"

# iOS AppIcon sizes (points * scale)
$IconSizes = @(
    @{ Size = 20; Scales = @(2,3) },
    @{ Size = 29; Scales = @(2,3) },
    @{ Size = 40; Scales = @(2,3) },
    @{ Size = 60; Scales = @(2,3) },
    @{ Size = 1024; Scales = @(1) } # App Store
)

# -----------------

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

foreach ($entry in $IconSizes) {
    foreach ($scale in $entry.Scales) {

        $px = $entry.Size * $scale
        $bmp = New-Object System.Drawing.Bitmap $px, $px
        $gfx = [System.Drawing.Graphics]::FromImage($bmp)

        $gfx.SmoothingMode = "AntiAlias"
        $gfx.TextRenderingHint = "AntiAliasGridFit"
        $gfx.Clear($Background)

        # Font size scaled to fill icon nicely
        $fontSize = $px * 0.75
        $font = New-Object System.Drawing.Font($FontName, $fontSize, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
        $brush = New-Object System.Drawing.SolidBrush $Foreground

        # Center glyph
        $format = New-Object System.Drawing.StringFormat
        $format.Alignment = "Center"
        $format.LineAlignment = "Center"

        $rect = New-Object System.Drawing.RectangleF 0, 0, $px, $px
        $gfx.DrawString($Glyph, $font, $brush, $rect, $format)

        $file = Join-Path $OutputDir "Icon-${($entry.Size)}@${scale}x.png"
        $bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Png)

        $gfx.Dispose()
        $bmp.Dispose()
    }
}

Write-Host "Icons generated in $OutputDir"
