# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

> ## ⚠️ 서버 보안 주의 사항 ⚠️
>
> **이 도구는 운영 중인 맞고 게임 서버에 SSH로 직접 접속합니다.**
>
> - **서버 보안에 절대 주의** — 접속 정보 및 세션 파일 외부 유출 금지
> - **관련 없는 작업 절대 불가** — `pm2 ls` 상태 수집 외 어떠한 명령도 실행하지 말 것
> - **서비스 중단 엄금** — pm2 재시작·중지·설정 변경·파일 수정 등 일체 금지
> - **코드 수정 시 반드시 검토** — `xshell_script.py`에서 서버로 전송하는 명령이 `pm2 ls`인지 확인 후 실행할 것

---

## 프로젝트 개요

두 가지 독립 모니터링 기능으로 구성:
1. **PM2 상태 수집** — 맞고 게임 서버 3대(Amazon Linux) SSH 접속 후 `pm2 ls` 결과를 `file/*.txt`에 저장
2. **DB 통계 수집** — Oracle DB `ADMIN_STATISTICS_BUY` 테이블에서 당일 포인트 통계를 `log.txt`에 기록

## 실행 방법

```powershell
# [PM2] 수동 실행 (로그인 상태, Xshell이 설치된 환경 필요)
C:\Python314\python.exe main.py

# [DB] 수동 실행 (_db_cred.ini 설정 후)
C:\Python314\python.exe db_monitor.py

# 실행 결과 로그 확인 (작업 스케줄러 자동 실행 후)
Get-Content D:\claude_work\matgo_server_report\log.txt -Tail 30

# PM2 스케줄러 즉시 테스트 실행
Start-ScheduledTask -TaskName "Matgo-Server-Check"
```

의존 패키지 설치:
```powershell
C:\Python314\python.exe -m pip install pywin32 pyautogui
C:\Python314\python.exe -m pip install oracledb
```

---

## DB 모니터링 (db_monitor.py)

### 설정: _db_cred.ini

`_db_cred.ini`는 DB 접속 정보를 보관하는 파일로 **git에 포함되지 않는다** (`.gitignore`에 등록).  
최초 1회 설정이 필요하다:

```powershell
# 템플릿 복사
Copy-Item _db_cred.ini.template _db_cred.ini
# 이후 메모장 등으로 _db_cred.ini 를 열어 실제 접속 정보 입력
notepad _db_cred.ini
```

`_db_cred.ini` 형식:
```ini
[cashwalk_dev]
host     = DB_HOST
port     = 1521
sid      = DB_SID
user     = DB_USER
password = DB_PASSWORD
```

> 접속 정보는 SQL Developer → CASHWALK_DEV 세션 속성에서 확인한다.  
> 비밀번호는 SQL Developer에 저장된 값을 사용한다.

### DB 보안 규칙

- **SELECT 전용** — `_QUERY` 상수에 SELECT 문만 포함; DML(INSERT/UPDATE/DELETE) 절대 금지
- **접속 정보 코드 직접 기재 금지** — 모든 접속 정보는 `_db_cred.ini`에서만 읽음
- `_db_cred.ini`는 git 커밋 금지, 공유 금지

### log.txt DB 출력 형식

```
DB_START 2026-05-29 08:05:00
  [ADMIN_STATISTICS_BUY] 당일 포인트 통계
  ----------------------------------------------
  reg_date        point_total
  ----------------------------------------------
  2026-05-29       12,345,678
  ----------------------------------------------
DB_END
```

오류 발생 시:
```
DB_ERROR 2026-05-29 08:05:00: <오류 내용>
```

---

## 핵심 아키텍처

### 두 개의 독립된 Python 런타임

| 파일 | 실행 환경 | 역할 |
|------|-----------|------|
| `main.py` | Python 3.14 (외부) | Xshell GUI 자동화 오케스트레이터 |
| `xshell_script.py` | Xshell 내장 Python | SSH 접속 + 터미널 읽기 (xsh 전역 객체 사용) |

두 파일은 `_done.txt` 파일을 통해 통신한다.  
`xshell_script.py`가 완료되면 `_done.txt`를 생성 → `main.py`가 폴링으로 감지 → Xshell 종료.

### 실행 흐름

```
main.py
  WakeScreen()              ← 화면 보호기 해제 (마우스 1px 이동)
  CheckPrerequisites()      ← 파일/경로 존재 확인
  LaunchXshellAndRunScript()
    subprocess.Popen(Xshell.exe)
    _FindXshellMainFrame()  ← startswith('Xshell8::MainFrame') 매칭
    _FindXshellFrameMgr()   ← 'Xshell8::FrameMgr' (비가시 창, 메뉴 보유)
    _TriggerRunScript()     ← PostMessage(MainFrame, WM_COMMAND, 509, 0)
    _FillFileDialog()       ← 클립보드 붙여넣기 + Enter
  WaitForDoneFile()         ← _done.txt 폴링 (최대 300초)
  _CloseXshell()            ← WM_CLOSE → taskkill fallback

xshell_script.py (Xshell 내장 Python에서 실행)
  ProcessSession() × 3
    _CopySessionToAsciiPath()   ← 한글 경로 우회: tmp/ 에 ASCII 파일명으로 복사
    xsh.Session.Open(tmp_path)
    xsh.Screen.Send("clear\r")  ← 이전 출력 제거
    xsh.Session.Sleep(10000)    ← SSH 접속 완료 대기 (10초)
    row_before = CurrentRow
    xsh.Screen.Send("pm2 ls\r")
    row_after = CurrentRow
    ReadRangeOutput(row_before+2, row_after-1)  ← 정밀 범위 추출
    xsh.Session.Close()
  SaveCombinedTextFile()    ← file/TIMESTAMP_cw_real_game.txt
  _done.txt 작성            ← main.py에 완료 신호
```

## Xshell 8 내장 Python 제약사항

`xshell_script.py`는 Xshell 내장 Python 인터프리터에서 실행되므로 표준 Python 3과 다르다:

- `ctypes` **불가** (`_ctypes` C 확장 미포함)
- `subprocess` **불가** (hang/timeout 발생)
- `WaitForString(str, timeout)` **불가** — 인수 1개만 허용, timeout 파라미터 없음
- `Screen.Timeout` **속성 없음**
- `os.environ["USERPROFILE"]` **불가** — `winreg`으로 읽어야 함 (한글 사용자명 환경)
- 대기는 모두 `xsh.Session.Sleep(ms)` 고정값으로 처리
- **`Main()` 자동 호출**: Xshell이 스크립트 실행 시 `Main()` 함수를 자동으로 호출한다.  
  파일 끝에 `Main()`을 명시적으로 추가하면 **이중 실행**되어 오류 발생 — 절대 추가하지 말 것.

## Win32 API 주요 사항

### Xshell 창 구조
- `Xshell8::MainFrame` (또는 `_0`, `_1` 등): 가시 창, `WM_COMMAND` 수신
- `Xshell8::FrameMgr`: **비가시 창**, Win32 메뉴 핸들 보유 (명령 ID 조회 대상)

Xshell이 재실행되면 클래스명이 `MainFrame_1`처럼 변하므로 반드시 `startswith('Xshell8::MainFrame')`으로 매칭한다.

### 스크립트 실행 명령 ID
`_SCRIPT_RUN_CMD_ID = 509` — Xshell 8 (Build 0095) "도구 > 스크립트 > 스크립트 실행" 메뉴 항목의 Win32 명령 ID. Xshell 버전 업그레이드 시 변경될 수 있다. 변경된 경우 `_FindMenuCommandId()`가 자동으로 탐색하여 새 ID를 찾는다.

### Python 3.14 + pywin32 제한
`win32gui.GetMenuString`, `win32gui.GetMenuItemID`, `win32gui.GetSubMenu`가 Python 3.14용 pywin32에 미포함.  
→ `ctypes.windll.user32`로 직접 호출하여 우회 (`_GetMenuString`, `_GetMenuItemID_ct`, `_GetSubMenu`).

### 파일 다이얼로그 입력 방식
`_FillFileDialog()`는 Edit 컨트롤 감지 실패 시 **클립보드 붙여넣기 + Enter** 방식으로 fallback한다.  
Xshell 8의 "열기" 다이얼로그에서 Edit 컨트롤이 감지되지 않는 것이 정상 동작이다.

## 설정값 변경

모든 경로/타임아웃은 `config.py`에서 관리한다. `xshell_script.py`는 Xshell 내장 Python 제약으로 `config.py`를 import할 수 없어 설정값이 인라인으로 중복 존재한다. 경로 변경 시 두 파일을 모두 수정해야 한다.

| 설정 | `config.py` | `xshell_script.py` |
|------|-------------|---------------------|
| 출력 폴더 | `OUTPUT_DIR` | `_OUTPUT_DIR` |
| 타임스탬프 형식 | `TIMESTAMP_FORMAT` | `_TIMESTAMP_FORMAT` |
| 세션 경로 | `SESSIONS` | `_SESSIONS` |
| SSH 대기 시간 | `SSH_CONNECT_TIMEOUT_MS` | `xsh.Session.Sleep(10000)` 하드코딩 |

## 출력 파일 형식

`file/YYYY-MM-DD HH-MM_cw_real_game.txt` (파일명에 `:` 불가 → `HH-MM` 형식)

```
##HEADER## 2026-05-29 08-00  |  Matgo Game Server Status
================================================================
[서버 1]  cw_real_game_1  [OK]
----------------------------------------------------------------
<pm2 ls 출력>
...
```

## 자동 실행 원리

### 실행 체인

```
Windows 작업 스케줄러
  ↓  매일 08:00 트리거  (태스크명: Matgo-Server-Check)
run_monitor.bat
  ↓  cd 프로젝트 폴더
  ↓  C:\Python314\python.exe "D:\claude_work\matgo_server_report\main.py" >> log.txt 2>&1
main.py
  ↓  화면 보호기 해제 → Xshell 실행 → WM_COMMAND(509) 전송
  ↓  파일 다이얼로그 자동 입력 → xshell_script.py 실행 대기
xshell_script.py  (Xshell 내장 Python)
  ↓  서버 3대 순차 접속 → pm2 ls 수집 → _done.txt 생성
main.py (재개)
  ↓  _done.txt 감지 → Xshell 종료 → 결과 출력 → log.txt 기록
```

### 작업 스케줄러 등록 조건

작업 스케줄러에서 반드시 아래 옵션으로 등록해야 GUI 자동화가 작동한다:

| 옵션 | 올바른 설정 | 이유 |
|------|-------------|------|
| 실행 조건 | **사용자가 로그온한 경우에만 실행** | 사용자 세션에서 실행되어야 Win32 창 조작 가능 |
| 최고 권한으로 실행 | 체크 불필요 | 일반 사용자 권한으로 충분 |
| 화면 보호기 잠금 | **비밀번호 없음** | `WakeScreen()`이 마우스 신호로 자동 해제 |
| 프로그램/스크립트 | `cmd.exe` | |
| 인수 추가 | `/c "D:\claude_work\matgo_server_report\run_monitor.bat"` | |
| 시작 위치 | `D:\claude_work\matgo_server_report` | |

로그 파일 위치: `D:\claude_work\matgo_server_report\log.txt`

### run_monitor.bat 편집 주의사항

`run_monitor.bat`은 반드시 **CRLF 줄 끝 + ANSI(CP949) 인코딩**으로 저장해야 한다.  
Claude Code의 Write 도구로 저장하면 LF 줄 끝이 되어 cmd가 줄을 제대로 파싱하지 못하고 `time` 명령이 인터랙티브로 실행되는 오류가 발생한다.

파일 수정 시 PowerShell로 저장:
```powershell
$content = "@echo off`r`ncd /d `"D:\claude_work\matgo_server_report`"`r`necho START >> log.txt`r`nC:\Python314\python.exe `"D:\claude_work\matgo_server_report\main.py`" >> log.txt 2>&1`r`necho END >> log.txt`r`n"
[System.IO.File]::WriteAllText("D:\claude_work\matgo_server_report\run_monitor.bat", $content, [System.Text.Encoding]::GetEncoding(949))
```

또한 `%date%`, `%time%` 환경 변수는 배치 파일에서 사용하지 않는다 (한국어 Windows에서 파싱 오류 발생 가능).

---

## 자동 실행 중지 방법

### 방법 1: 일시 중지 (나중에 재개 가능)

```powershell
# 태스크 이름 확인
Get-ScheduledTask | Where-Object { $_.TaskName -like "*Matgo*" }

# 일시 비활성화 (트리거·설정 유지)
Disable-ScheduledTask -TaskName "Matgo-Server-Check"

# 다시 활성화
Enable-ScheduledTask -TaskName "Matgo-Server-Check"
```

### 방법 2: GUI로 중지

1. 시작 메뉴 → **작업 스케줄러** 검색 후 실행
2. 좌측 트리: **작업 스케줄러 라이브러리**
3. 우측 목록에서 `Matgo-Server-Check` 찾기
4. 우클릭 → **사용 안 함** (비활성화) 또는 **삭제**

### 방법 3: 이미 실행 중일 때 즉시 중단

```powershell
# Xshell 강제 종료 (xshell_script.py 실행 중일 때)
taskkill /f /im Xshell.exe

# main.py 프로세스 강제 종료
taskkill /f /im python.exe
```

> **주의**: `taskkill /f /im python.exe`는 실행 중인 모든 Python 프로세스를 종료한다.  
> 다른 Python 작업이 실행 중이라면 PID를 확인 후 선택 종료한다:
> ```powershell
> Get-Process python | Select-Object Id, StartTime, MainWindowTitle
> taskkill /f /pid <PID>
> ```

### 방법 4: 영구 삭제

```powershell
Unregister-ScheduledTask -TaskName "Matgo-Server-Check" -Confirm:$false
```

재등록이 필요할 때는 작업 스케줄러 GUI에서 직접 등록한다 (PowerShell `Set-ScheduledTask`는 관리자 권한 필요).
