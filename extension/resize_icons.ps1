Add-Type -AssemblyName System.Drawing

$srcPath = 'C:\Users\82104\.gemini\antigravity\brain\507e0f91-ef79-4de6-871a-2f1972c354cc\soma_mate_icon_1780365848308.png'
$tempDir = 'C:\Users\82104\soma_icons_temp'

if (!(Test-Path $tempDir)) {
    New-Item -ItemType Directory -Path $tempDir -Force
}

$src = [System.Drawing.Image]::FromFile($srcPath)

foreach ($size in @(16, 48, 128)) {
    $bmp = New-Object System.Drawing.Bitmap($size, $size)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.DrawImage($src, 0, 0, $size, $size)
    $g.Dispose()
    $outPath = Join-Path $tempDir "icon$size.png"
    $bmp.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    Write-Host "Created $outPath"
}

$src.Dispose()
Write-Host 'All icons created'
