$ErrorActionPreference = "Stop"

# Windows 빌드 스크립트 (PyInstaller)

$name = "AnalystRecom"
$entry = "main_gui.py"
$workdir = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $workdir

# 번들 리소스(config/data)를 함께 포함합니다.
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

