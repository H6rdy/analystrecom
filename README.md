## AnalystRecom (S&P 500 기관 투자의견 스크리닝 + 텔레그램 알림)

PyQt6 기반의 다크 테마 데스크톱 앱에서 S&P 500 종목의 기관 투자의견/목표가 정보를 스크리닝하고,
사용자 포트폴리오의 **등급 하향** 또는 **목표가 변경**을 감지하면 텔레그램으로 알림을 발송합니다.

### 프로젝트 구조

```text
analystrecom/
  .github/
    workflows/
      update.yml
  config/
    app_config.json
    portfolio.json
  data/
    latest_data.json
    previous_data.json
  backend.py
  main_gui.py
  requirements.txt
  LICENSE
  README.md
```

### 설치

Windows PowerShell 기준:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 실행

```bash
python main_gui.py
```

### GitHub Actions 데이터 갱신

워크플로(`.github/workflows/update.yml`)는 매일 **KST 오전 8시**에 데이터를 갱신해 `data/latest_data.json`을 업데이트하도록 설정되어 있습니다.
(GitHub cron은 UTC 기준이므로 `0 23 * * *`로 동작합니다.)

### 텔레그램 알림 설정

`config/app_config.json`에 아래 값을 넣으세요.

- `telegram.bot_token`: BotFather로 발급
- `telegram.chat_id`: 알림 받을 채팅(개인/그룹) ID

### 포트폴리오 수정

앱 좌측 사이드바에서 `Watched Tickers` 목록에 `Add / Remove Selected`로 종목을 추가/삭제할 수 있고,
변경은 `config/portfolio.json`(사용자 저장소)에 즉시 반영됩니다.

### 실행 파일 패키징 (PyInstaller, Windows)

1. 개발 의존성 설치:

```bash
pip install -r dev_requirements.txt
```

2. 실행 파일 빌드:

```powershell
.\package_exe.ps1
```

빌드 결과는 `dist/AnalystRecom.exe`에 생성됩니다.

### 실행 파일에서 최신 데이터 자동 동기화

실행 파일로 패키징하면 번들된 `latest_data.json`이 고정이라, 앱 시작 시 GitHub `raw` URL에서 최신 스냅샷을 다운로드하도록 되어 있습니다.

1. `config/app_config.json`의 `app.remote_latest_data.latest_data_url`에 아래 형식으로 넣으세요.

```text
https://raw.githubusercontent.com/<GITHUB_USER>/<GITHUB_REPO>/<BRANCH>/main/data/latest_data.json
```

2. 동일하게 `ANALYSTRECOM_LATEST_DATA_URL` 환경변수를 지정해도 됩니다.

