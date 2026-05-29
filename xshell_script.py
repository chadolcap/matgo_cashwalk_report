# xshell_script.py
# Xshell built-in Python automation script for matgo server monitoring.
# Usage: Xshell > Tools > Script > Run Script > select this file
#
# !! 보안 주의 사항 !!
#   - 서버 보안에 절대 주의
#   - 서버 접속 후 관련 없는 작업 절대 불가 (pm2 ls 수집만 허용)
#   - 서비스에 지장을 주는 행위 엄금 (재시작/중지/설정 변경 금지)
#
# Constraints of Xshell built-in Python:
#   - ctypes      : NOT available (_ctypes module missing)
#   - subprocess  : NOT available (hangs/timeout)
#   - winreg      : available
#   - shutil      : available (pure Python)

import os
import shutil
import winreg
from datetime import datetime

# ─── Settings ────────────────────────────────────────────────────────────────

_OUTPUT_DIR       = r"D:\claude_work\matgo_server_report\file"
_TMP_DIR          = r"D:\claude_work\matgo_server_report\tmp"
_DONE_FILE        = r"D:\claude_work\matgo_server_report\_done.txt"
_TIMESTAMP_FORMAT = "%Y-%m-%d %H-%M"  # ':' is forbidden in Windows filenames

# Xshell 8 API constraints (Build 0095):
#   WaitForString(string)  - 1 arg only, no timeout param
#   Screen.Timeout         - property does NOT exist
# Timeout handled by fixed Sleep values.


def _GetUserProfile():
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Volatile Environment")
        v, _ = winreg.QueryValueEx(k, "USERPROFILE")
        winreg.CloseKey(k)
        return v
    except Exception:
        return "C:\\Users\\Default"


def _CopySessionToAsciiPath(src_path, session_name):
    """Unicode 경로 세션 파일을 ASCII tmp 경로로 복사 (xsh.Session.Open 우회)"""
    os.makedirs(_TMP_DIR, exist_ok=True)
    tmp_path = _TMP_DIR + "\\" + session_name + ".xsh"
    shutil.copy2(src_path, tmp_path)
    return tmp_path


_userprofile  = _GetUserProfile()
_SESSION_BASE = (
    _userprofile
    + "\\Documents\\NetSarang Computer\\8\\Xshell\\Sessions\\CW_MATGO_REAL"
)

_SESSIONS = [
    {"name": "cw_real_game_1", "path": _SESSION_BASE + "\\cw_real_game_1.xsh"},
    {"name": "cw_real_game_2", "path": _SESSION_BASE + "\\cw_real_game_2.xsh"},
    {"name": "cw_real_game_3", "path": _SESSION_BASE + "\\cw_real_game_3.xsh"},
]


# ─── 터미널 읽기 ─────────────────────────────────────────────────────────────

def GetTimestamp():
    return datetime.now().strftime(_TIMESTAMP_FORMAT)


def ReadRangeOutput(start_row, end_row):
    """
    start_row ~ end_row 범위만 읽어 pm2 ls 출력을 깨끗하게 추출합니다.
    빈 줄만 있는 행은 보존하되, 전체 공백(스페이스만) 행은 제거합니다.
    """
    lines = []
    try:
        cols = xsh.Screen.Columns
        for row in range(start_row, end_row + 1):
            line = xsh.Screen.Get(row, 1, row, cols)
            lines.append(line.rstrip())
    except Exception as e:
        lines.append("[screen read error] " + str(e))

    # 앞뒤 빈 줄 제거
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    return "\n".join(lines)


# ─── 통합 파일 저장 ───────────────────────────────────────────────────────────

def SaveCombinedTextFile(session_results, timestamp):
    """
    3개 세션의 pm2 ls 출력을 하나의 txt 파일로 저장합니다.
    파일명: TIMESTAMP_cw_real_game.txt

    출력 형식:
      ##HEADER## ...
      ━━━━━━━━━━━ (구분선)
      [서버 1]  cw_real_game_1  [OK]
      ─────────────────────────────
      <pm2 ls 출력>

      [서버 2]  cw_real_game_2  [OK]
      ...
    """
    filename = timestamp + "_cw_real_game.txt"
    txt_path = os.path.join(_OUTPUT_DIR, filename)

    thick = "=" * 64
    thin  = "-" * 64

    lines = []
    lines.append("##HEADER## " + timestamp + "  |  Matgo Game Server Status")
    lines.append(thick)
    lines.append("")

    for i, item in enumerate(session_results):
        num    = str(i + 1)
        status = "[OK]" if item["success"] else "[NG]"
        lines.append("[서버 " + num + "]  " + item["name"] + "  " + status)
        lines.append(thin)
        if item["text"]:
            lines.append(item["text"])
        else:
            lines.append("  (데이터 없음: " + item["message"] + ")")
        lines.append("")

    lines.append(thick)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return txt_path


# ─── 세션 처리 ───────────────────────────────────────────────────────────────

def ProcessSession(session_info):
    """
    SSH 접속 → clear → pm2 ls → 출력 범위만 읽기 → 세션 종료

    Returns:
        (success: bool, message: str, terminal_text: str)
    """
    session_name = session_info["name"]
    session_path = session_info["path"]
    tmp_path     = None

    if not os.path.exists(session_path):
        return False, "session file not found: " + session_path, ""

    try:
        # 1. ASCII tmp 경로로 세션 파일 복사 후 열기
        tmp_path = _CopySessionToAsciiPath(session_path, session_name)
        xsh.Session.Open(tmp_path)
        xsh.Screen.Synchronous = True

        # 2. SSH 접속 + Amazon Linux 로그인 배너 완료 대기 (10초)
        xsh.Session.Sleep(10000)

        # 3. clear: 이전 내용 제거 → pm2 ls 출력만 남기기 위함
        xsh.Screen.Send("clear")
        xsh.Screen.Send("\r")
        xsh.Session.Sleep(1500)

        # 4. pm2 ls 실행 직전 행 번호 기록
        row_before = xsh.Screen.CurrentRow

        # 5. pm2 ls 실행
        xsh.Screen.Send("pm2 ls")
        xsh.Screen.Send("\r")
        xsh.Session.Sleep(4000)

        # 6. pm2 ls 완료 후 행 번호 기록
        row_after = xsh.Screen.CurrentRow

        # 7. pm2 ls 출력 범위만 추출
        #    row_before + 1: "pm2 ls" 에코 줄
        #    row_before + 2: pm2 테이블 첫 번째 줄  ← 여기서 시작
        #    row_after  - 1: 마지막 프롬프트 줄 제외
        pm2_start = row_before + 2
        pm2_end   = row_after  - 1

        if pm2_start <= pm2_end:
            terminal_text = ReadRangeOutput(pm2_start, pm2_end)
        else:
            # fallback: 전체 읽기
            terminal_text = ReadRangeOutput(
                max(1, row_after - 50), row_after
            )

        # 8. 세션 종료
        xsh.Session.Close()
        xsh.Session.Sleep(1000)

        return True, "OK", terminal_text

    except Exception as e:
        try:
            xsh.Session.Close()
        except Exception:
            pass
        return False, session_name + " error: " + str(e), ""

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


# ─── Entry point ─────────────────────────────────────────────────────────────

def Main():
    """Xshell이 스크립트 실행 시 자동 호출"""
    timestamp = GetTimestamp()
    results   = []

    for session_info in _SESSIONS:
        success, message, terminal_text = ProcessSession(session_info)
        results.append({
            "name":    session_info["name"],
            "success": success,
            "message": message,
            "text":    terminal_text,
        })

    # 통합 txt 저장
    combined_path = SaveCombinedTextFile(results, timestamp)

    # _done.txt: main.py 완료 신호
    success_count = sum(1 for r in results if r["success"])
    total_count   = len(results)

    done_lines = [str(success_count) + "/" + str(total_count)]
    done_lines.append("saved: " + combined_path)
    for r in results:
        status = "OK" if r["success"] else "NG"
        done_lines.append(status + " " + r["name"] + ": " + r["message"])

    with open(_DONE_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(done_lines))

    # MsgBox 없이 종료 → main.py가 _done.txt 감지 후 자동 진행
    # Xshell이 Main()을 자동 호출하므로 명시적 호출 불필요
