$ErrorActionPreference = "Stop"

$name = "AnalystRecom"
$entry = "main_gui.py"
$workdir = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $workdir

pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name $name `
  --add-data "config\app_config.json;config" `
  --add-data "config\portfolio.json;config" `
  --add-data "data\latest_data.json;data" `
  --add-data "data\previous_data.json;data" `
  --hidden-import PyQt6.sip `
  $entry

Pop-Location

Write-Host "Build finished."
Write-Host "Output: .\dist\$name.exe"