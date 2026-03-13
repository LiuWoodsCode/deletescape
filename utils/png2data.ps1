param([string]$path)

$bytes = [System.IO.File]::ReadAllBytes($path)
$base64 = [Convert]::ToBase64String($bytes)
$mime = "image/png"

Write-Output "data:$mime;base64,$base64"