param(
  [Parameter(Mandatory=$true)][string]$DataPack,
  [string]$OutputDir = "dist"
)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Data = Resolve-Path $DataPack
$Out = Join-Path $Root $OutputDir
New-Item -ItemType Directory -Force -Path $Out | Out-Null

py -3 -m pip install --upgrade pip
py -3 -m pip install "pyinstaller>=6.11,<7"

Copy-Item $Data (Join-Path $PSScriptRoot "ThaiFDA_DataPack.zip") -Force
try {
  Push-Location $PSScriptRoot
  $Args = @(
    "-3","-m","PyInstaller",
    "--noconfirm","--clean","--onefile","--windowed",
    "--name","ThaiFDA_LocalMoE_Setup",
    "--add-data","ThaiFDA_DataPack.zip;.",
    "setup_app.py"
  )
  & py @Args
  if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
  Copy-Item ".\dist\ThaiFDA_LocalMoE_Setup.exe" (Join-Path $Out "ThaiFDA_LocalMoE_Setup.exe") -Force
}
finally {
  Pop-Location
  Remove-Item (Join-Path $PSScriptRoot "ThaiFDA_DataPack.zip") -Force -ErrorAction SilentlyContinue
}
Write-Host "Built: $(Join-Path $Out 'ThaiFDA_LocalMoE_Setup.exe')"
