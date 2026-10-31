param(
  [Parameter(Mandatory=$true)][string]$ExePath,
  [Parameter(Mandatory=$true)][string]$PfxPath,
  [Parameter(Mandatory=$true)][string]$PfxPassword,
  [string]$TimestampUrl = "http://timestamp.digicert.com"
)
$ErrorActionPreference = "Stop"
$Exe = Resolve-Path $ExePath
$Pfx = Resolve-Path $PfxPath
$SignTool = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" -Filter signtool.exe -Recurse |
  Where-Object { $_.FullName -match "\\x64\\signtool.exe$" } |
  Sort-Object FullName -Descending | Select-Object -First 1
if (-not $SignTool) { throw "signtool.exe not found. Install Windows SDK." }
& $SignTool.FullName sign /fd SHA256 /f $Pfx /p $PfxPassword /tr $TimestampUrl /td SHA256 /d "Local MoE Studio - Thai FDA Edition" $Exe
if ($LASTEXITCODE -ne 0) { throw "Signing failed" }
& $SignTool.FullName verify /pa /v $Exe
if ($LASTEXITCODE -ne 0) { throw "Signature verification failed" }
Write-Host "Signed and verified: $Exe"
