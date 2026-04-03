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

## 실행 가이드 (매우 상세)

아래 가이드는 **개발 실행(소스 실행)**과 **배포 실행(EXE 실행)**을 모두 포함합니다.

---

### 1) 사전 준비

#### 1-1. 요구 사항
- OS: Windows 10/11
- Python: 3.12+ 권장
- 인터넷 연결 (finviz 데이터 수집/원격 JSON 동기화 시 필요)
- GitHub 저장소 접근 가능

#### 1-2. PowerShell 실행 정책 이슈가 있을 때
가상환경 활성화(`Activate.ps1`)가 막히면 1회 실행:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

### 2) 프로젝트 내려받기/이동

```powershell
cd C:\Users\<사용자명>\Desktop
git clone https://github.com/H6rdy/analystrecom.git
cd analystrecom
```

---

### 3) 개발 모드 실행 (소스 실행)

#### 3-1. 가상환경 생성 및 활성화

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

성공하면 프롬프트 앞에 `(.venv)`가 표시됩니다.

#### 3-2. 의존성 설치

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

#### 3-3. 앱 설정 파일 편집
편집 파일: `config/app_config.json`

기본적으로 아래 항목을 확인하세요:
- `app.sync_on_start`: 앱 시작 시 데이터 동기화
- `app.remote_latest_data.enabled`: 원격 최신 JSON 자동 다운로드 여부
- `app.remote_latest_data.latest_data_url`: 최신 JSON 원격 URL
- `telegram.enabled`: 텔레그램 알림 사용 여부

#### 3-4. 원격 최신 데이터 URL 설정
아래 값으로 설정하면 됩니다.

```text
https://raw.githubusercontent.com/H6rdy/analystrecom/main/data/latest_data.json
```

`config/app_config.json` 예시:

```json
"remote_latest_data": {
  "enabled": true,
  "latest_data_url": "https://raw.githubusercontent.com/H6rdy/analystrecom/main/data/latest_data.json",
  "timeout_sec": 20
}
```

#### 3-5. 실행

```powershell
python main_gui.py
```

---

### 4) 앱 사용 방법

#### 4-1. 포트폴리오 수정
좌측 사이드바 `Watched Tickers`에서:
- 입력창에 티커 입력 (`AAPL`, `MSFT` 등)
- `Add` 버튼으로 추가
- 목록 선택 후 `Remove Selected`로 삭제

저장은 즉시 반영되며, 사용자 저장소의 아래 파일에 기록됩니다:
- `%LOCALAPPDATA%\analystrecom\config\portfolio.json`

#### 4-2. 데이터 갱신
- `Refresh`: 로컬 동기화/화면 새로고침
- `Live Fetch`: finviz에서 즉시 수집

#### 4-3. 알림 테스트
- 포트폴리오 구성 후 `Run Alerts` 클릭
- 하향/목표가 변경 이벤트가 있으면 알림 처리

---

### 5) 텔레그램 알림 설정

`config/app_config.json`의 `telegram`을 채우세요.

```json
"telegram": {
  "enabled": true,
  "bot_token": "<BOTFATHER_TOKEN>",
  "chat_id": "<CHAT_ID>"
}
```

- `bot_token`: BotFather에서 발급
- `chat_id`: 개인/그룹 채팅 ID

주의:
- 실행 파일에서는 사용자 저장소의 설정(`%LOCALAPPDATA%\analystrecom\config\app_config.json`)이 우선 사용됩니다.

---

### 6) 실행 파일(EXE) 패키징 및 실행

#### 6-1. 빌드 의존성 설치

```powershell
python -m pip install -r dev_requirements.txt
```

#### 6-2. EXE 빌드

```powershell
.\package_exe.ps1
```

생성 결과:
- `dist/AnalystRecom.exe`

#### 6-3. EXE 실행
탐색기에서 `dist/AnalystRecom.exe`를 더블클릭하거나:

```powershell
.\dist\AnalystRecom.exe
```

---

### 7) 실행 파일에서 데이터/설정이 저장되는 실제 위치

앱은 실행 시 사용자 쓰기 가능 경로를 사용합니다:

- 루트: `%LOCALAPPDATA%\analystrecom`
- 설정: `%LOCALAPPDATA%\analystrecom\config\app_config.json`
- 포트폴리오: `%LOCALAPPDATA%\analystrecom\config\portfolio.json`
- 최신 데이터: `%LOCALAPPDATA%\analystrecom\data\latest_data.json`
- 이전 데이터: `%LOCALAPPDATA%\analystrecom\data\previous_data.json`

즉, EXE를 어디에 복사해도 실제 사용자 데이터는 위 경로에 유지됩니다.

---

### 8) GitHub Actions 자동 갱신

워크플로 파일:
- `.github/workflows/update.yml`

동작:
- 매일 KST 08:00 실행 (UTC cron `0 23 * * *`)
- `data/latest_data.json` 갱신 후 커밋

확인 절차:
1. GitHub 저장소의 `Actions` 탭 열기
2. `Update latest_data.json` 워크플로 성공 여부 확인
3. `data/latest_data.json` 파일의 최근 커밋 시간 확인

---

### 9) 문제 해결 (Troubleshooting)

#### 9-1. 앱 실행은 되는데 테이블이 비어 있음
- `data/latest_data.json`의 `rows`가 비어있는지 확인
- `Live Fetch` 실행 후 다시 확인
- 네트워크 제한 환경이면 원격 동기화 URL 사용 여부 확인

#### 9-2. 원격 자동 동기화가 안 됨
- `%LOCALAPPDATA%\analystrecom\config\app_config.json`에서 URL이 실제로 입력됐는지 확인
- 브라우저에서 URL 직접 열어 JSON이 내려오는지 확인
- `timeout_sec` 값을 20 -> 40으로 높여 재시도

#### 9-3. 텔레그램이 안 옴
- `telegram.enabled`가 `true`인지 확인
- `bot_token`, `chat_id` 오타 확인
- 봇이 해당 채팅에 메시지를 보낼 권한이 있는지 확인

#### 9-4. 패키징 후 실행 오류
- 반드시 빌드 전에 `dev_requirements.txt` 설치
- 기존 `dist/`, `build/`를 지운 후 재빌드:

```powershell
Remove-Item -Recurse -Force .\dist, .\build
.\package_exe.ps1
```

---

### 10) 빠른 시작 체크리스트

1. `pip install -r requirements.txt`
2. `config/app_config.json`에서 원격 URL/텔레그램 설정
3. `python main_gui.py` 실행
4. 포트폴리오 추가/삭제 확인
5. 필요 시 `.\package_exe.ps1`로 EXE 빌드


