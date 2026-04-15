$ErrorActionPreference = "Stop"

# Windows 빌드 스크립트 (PyInstaller)

param(
  [switch] $SkipInstall
)

$name = "AnalystRecom"
$entry = "main_gui.py"
$workdir = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $workdir

# 가능한 경우 로컬 가상환경의 python을 사용합니다.
$venvPy = Join-Path $workdir ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
  $py = $venvPy
} else {
  $py = "python"
}

if (-not $SkipInstall) {
  & $py -m pip install --upgrade pip
  & $py -m pip install -r "dev_requirements.txt"
}

# 번들 리소스(config/data)를 함께 포함합니다.
# PyInstaller 패키지 모듈명은 `PyInstaller`입니다.
& $py -m PyInstaller `
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

