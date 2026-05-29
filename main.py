# -*- coding: utf-8 -*-
"""
Matgo Server Monitor - Orchestrator
Usage: python main.py

Flow:
  1. _done.txt 초기화
  2. Xshell 실행
  3. Xshell8::FrameMgr (비가시) 메뉴에서 '스크립트 실행' 명령 ID 탐색
  4. Xshell8::MainFrame (가시)에 PostMessage(WM_COMMAND, 509) 전송
  5. 파일 다이얼로그 자동 입력
  6. _done.txt 폴링 대기 (xshell_script.py 완료 신호)
  7. Xshell 자동 종료 → 결과 출력
"""

import subprocess
import sys
import os
import time
import ctypes

import win32gui
import win32con
import win32api
import win32clipboard
import pyautogui

# UTF-8 출력 (PowerShell CP949 오류 방지)
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, r"D:\claude_work\matgo_server_report")
from config import (
    XSHELL_EXE,
    XSHELL_SCRIPT,
    OUTPUT_DIR,
    SESSIONS,
    PYTHON_EXE,
)

DONE_FILE        = r"D:\claude_work\matgo_server_report\_done.txt"
MAX_WAIT_SECONDS = 300

# ─── ctypes 메뉴 API (win32gui.GetMenuString 누락 대응) ──────────────────────
# Python 3.14용 pywin32에 GetMenuString/GetMenuItemID/GetSubMenu 미포함
# → user32.dll 직접 호출

_u32          = ctypes.windll.user32
_MF_BYPOSITION = 0x00000400


def _GetMenuString(hmenu: int, idx: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _u32.GetMenuStringW(hmenu, idx, buf, 256, _MF_BYPOSITION)
    return buf.value


def _GetMenuItemID_ct(hmenu: int, idx: int) -> int:
    return _u32.GetMenuItemID(hmenu, idx)


def _GetSubMenu(hmenu: int, idx: int) -> int:
    return _u32.GetSubMenu(hmenu, idx)


def _EnumMenuItems(hmenu: int, depth: int = 0) -> list:
    """메뉴를 재귀적으로 열거합니다. Returns: [(depth, text, item_id), ...]"""
    results = []
    if not hmenu:
        return results
    try:
        count = win32gui.GetMenuItemCount(hmenu)
    except Exception:
        return results
    for i in range(count):
        try:
            text    = _GetMenuString(hmenu, i)
            item_id = _GetMenuItemID_ct(hmenu, i)
            results.append((depth, text, item_id))
            sub = _GetSubMenu(hmenu, i)
            if sub:
                results.extend(_EnumMenuItems(sub, depth + 1))
        except Exception:
            pass
    return results


# ─── Prerequisite checks ─────────────────────────────────────────────────────

def CheckPrerequisites() -> bool:
    checks = [
        (XSHELL_EXE,    "Xshell 8"),
        (XSHELL_SCRIPT, "xshell_script.py"),
        (OUTPUT_DIR,    "output dir"),
        (PYTHON_EXE,    "Python 3.14"),
    ]
    all_ok = True
    print("\n[Check]")
    for path, desc in checks:
        exists = os.path.exists(path)
        print(f"  {'[OK]' if exists else '[NG]'} {desc}: {path}")
        if not exists:
            all_ok = False

    print("\n[Sessions]")
    for s in SESSIONS:
        exists = os.path.exists(s["path"])
        print(f"  {'[OK]' if exists else '[NG]'} {s['name']}: {s['path']}")
        if not exists:
            all_ok = False

    return all_ok


# ─── Xshell 전용 창 탐색 ─────────────────────────────────────────────────────

def _FindXshellMainFrame():
    """
    Xshell8 메인 프레임 가시 창 탐색.
    다중 인스턴스 시 클래스명이 MainFrame_0, MainFrame_1 등으로 변하므로
    prefix 매칭 사용.
    """
    found = []
    def cb(hwnd, _):
        if (win32gui.IsWindowVisible(hwnd) and
                win32gui.GetClassName(hwnd).startswith('Xshell8::MainFrame')):
            found.append(hwnd)
    win32gui.EnumWindows(cb, None)
    return found[0] if found else None


def _FindXshellFrameMgr():
    """Xshell8::FrameMgr 비가시 창 (Win32 메뉴 보유, 명령 ID 조회용)"""
    found = []
    def cb(hwnd, _):
        if win32gui.GetClassName(hwnd) == 'Xshell8::FrameMgr':
            found.append(hwnd)
    win32gui.EnumWindows(cb, None)
    return found[0] if found else None


def _FocusWindow(hwnd) -> None:
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(hwnd)
    time.sleep(0.5)


# ─── 메뉴 명령 트리거 ────────────────────────────────────────────────────────

def _FindMenuCommandId(frame_mgr_hwnd: int, keywords: list):
    """
    FrameMgr 메뉴에서 키워드를 포함한 명령 ID를 반환합니다.
    """
    hmenu = win32gui.GetMenu(frame_mgr_hwnd)
    if not hmenu:
        print(f"  [NG] FrameMgr GetMenu 실패 (hwnd={frame_mgr_hwnd})")
        return None

    items = _EnumMenuItems(hmenu)
    print(f"  [INFO] 메뉴 항목 {len(items)}개 탐색")

    for _depth, text, item_id in items:
        if item_id > 0:
            for kw in keywords:
                if kw in text:
                    print(f"  [OK] 발견: {repr(text)} ID={item_id}")
                    return item_id

    print("  [NG] 키워드 매칭 실패")
    return None


_SCRIPT_RUN_CMD_ID = 509  # Xshell 8 '스크립트 실행' 명령 ID (debug_menu2.py로 검증)


def _TriggerRunScript(main_frame_hwnd: int, frame_mgr_hwnd: int) -> bool:
    """
    FrameMgr 메뉴에서 '스크립트 실행' ID를 탐색 후
    MainFrame에 PostMessage(WM_COMMAND)를 전송합니다.
    FrameMgr 탐색 실패 시 검증된 ID=509로 fallback합니다.
    """
    item_id = None

    if frame_mgr_hwnd:
        keywords = ["스크립트 실행", "Run Script"]
        item_id = _FindMenuCommandId(frame_mgr_hwnd, keywords)

    if item_id is None:
        print(f"  [INFO] FrameMgr 메뉴 탐색 실패 → 기본 ID={_SCRIPT_RUN_CMD_ID} 사용")
        item_id = _SCRIPT_RUN_CMD_ID

    print(f"  [OK] PostMessage({main_frame_hwnd}, WM_COMMAND, {item_id}, 0)")
    win32gui.PostMessage(main_frame_hwnd, win32con.WM_COMMAND, item_id, 0)
    time.sleep(1.5)  # 파일 다이얼로그 열릴 때까지 대기
    return True


# ─── 파일 다이얼로그 자동 입력 ────────────────────────────────────────────────

_DIALOG_TITLE_KEYWORDS = [
    "열기", "Open", "Run Script",
    "스크립트 실행", "스크립트", "Script",
]


def _FillFileDialog(script_path: str) -> bool:
    """
    파일 선택 다이얼로그에 스크립트 경로를 입력하고 확인합니다.
    1차: Edit 컨트롤 WM_SETTEXT + WM_COMMAND(IDOK)
    2차: 클립보드 붙여넣기 + Enter
    """
    # ── 다이얼로그 감지 (최대 10초) ──────────────────────────────────────────
    dialog_hwnd = None
    print("  [INFO] 파일 다이얼로그 감지 중", end="", flush=True)
    for _ in range(34):
        for kw in _DIALOG_TITLE_KEYWORDS:
            h = None
            found_list = []
            def _cb(hwnd, _):
                if win32gui.IsWindowVisible(hwnd) and kw in win32gui.GetWindowText(hwnd):
                    found_list.append(hwnd)
            win32gui.EnumWindows(_cb, None)
            if found_list:
                dialog_hwnd = found_list[0]
                title = win32gui.GetWindowText(dialog_hwnd)
                print(f"\n  [OK] 다이얼로그 감지: {repr(title)} (hwnd={dialog_hwnd})")
                break
        if dialog_hwnd:
            break
        print(".", end="", flush=True)
        time.sleep(0.3)

    if not dialog_hwnd:
        print("\n  [NG] 파일 다이얼로그를 찾지 못했습니다 (10초 초과)")
        return False

    time.sleep(0.3)

    # ── 1차: Edit 컨트롤 → WM_SETTEXT + IDOK ────────────────────────────────
    edit_hwnd = win32gui.FindWindowEx(dialog_hwnd, None, "Edit", None)
    if edit_hwnd:
        print(f"  [INFO] Edit 컨트롤 (hwnd={edit_hwnd}) → WM_SETTEXT")
        win32gui.SendMessage(edit_hwnd, win32con.WM_SETTEXT, 0, script_path)
        time.sleep(0.3)
        win32api.SendMessage(dialog_hwnd, win32con.WM_COMMAND, 1, 0)  # IDOK=1
        print("  [OK] WM_SETTEXT + WM_COMMAND(IDOK) 전송")
        return True

    # ── 2차: 클립보드 붙여넣기 fallback ─────────────────────────────────────
    print("  [WARN] Edit 컨트롤 없음 → 클립보드 붙여넣기")
    _FocusWindow(dialog_hwnd)
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(script_path, win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
    except Exception as ce:
        print(f"  [WARN] 클립보드 오류: {ce}")

    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.1)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.3)
    pyautogui.press('enter')
    print("  [OK] 클립보드 붙여넣기 + Enter")
    return True


# ─── Xshell 실행 및 스크립트 트리거 ─────────────────────────────────────────

def LaunchXshellAndRunScript() -> bool:
    """
    Xshell 실행 → FrameMgr 메뉴 API로 '스크립트 실행' → 파일 다이얼로그 자동 입력
    """
    print(f"\n[Xshell] 실행 중: {XSHELL_EXE}")
    subprocess.Popen([XSHELL_EXE])

    # ── 1단계: MainFrame(가시) 대기 ─────────────────────────────────────────
    main_frame_hwnd = None
    print("  [INFO] Xshell MainFrame 대기", end="", flush=True)
    for _ in range(40):          # 최대 20초
        main_frame_hwnd = _FindXshellMainFrame()
        if main_frame_hwnd:
            print(f"\n  [OK] MainFrame 감지: hwnd={main_frame_hwnd}")
            break
        print(".", end="", flush=True)
        time.sleep(0.5)

    if not main_frame_hwnd:
        print(f"\n  [NG] 20초 내 Xshell MainFrame 감지 실패")
        return False

    # ── 2단계: FrameMgr(메뉴 보유) 탐색 ─────────────────────────────────────
    frame_mgr_hwnd = _FindXshellFrameMgr()
    if frame_mgr_hwnd:
        print(f"  [OK] FrameMgr 감지: hwnd={frame_mgr_hwnd}")
    else:
        print(f"  [WARN] FrameMgr 없음 - ID={_SCRIPT_RUN_CMD_ID} fallback 사용")

    _FocusWindow(main_frame_hwnd)
    time.sleep(0.5)

    # ── Win32 메뉴 API → '스크립트 실행' 트리거 ─────────────────────────────
    print("  [INFO] '스크립트 실행' 명령 전송...")
    if not _TriggerRunScript(main_frame_hwnd, frame_mgr_hwnd):
        print("  [NG] 스크립트 실행 트리거 실패")
        return False

    # ── 파일 다이얼로그 자동 입력 ────────────────────────────────────────────
    print(f"  [INFO] 스크립트 경로 입력: {XSHELL_SCRIPT}")
    ok = _FillFileDialog(XSHELL_SCRIPT)
    if ok:
        print("  [OK] 스크립트 실행 트리거 완료")
    return ok


# ─── _done.txt 폴링 ──────────────────────────────────────────────────────────

def WaitForDoneFile(timeout_sec: int = MAX_WAIT_SECONDS) -> bool:
    print(f"\n[Waiting] _done.txt 최대 {timeout_sec}초 대기...")
    start = time.time()
    while time.time() - start < timeout_sec:
        if os.path.exists(DONE_FILE):
            elapsed = int(time.time() - start)
            print(f"\n  [OK] 완료 신호 수신 ({elapsed}초)")
            return True
        elapsed = int(time.time() - start)
        print(f"\r  {elapsed}초 경과...", end="", flush=True)
        time.sleep(2)
    print(f"\n  [NG] 타임아웃 ({timeout_sec}초)")
    return False


# ─── Xshell 종료 ─────────────────────────────────────────────────────────────

def _CloseXshell() -> None:
    """
    Xshell을 종료합니다.
    1차: WM_CLOSE 전송 (정상 종료)
    2차: 3초 내 미종료 시 taskkill 강제 종료
    """
    print("\n[Xshell] 종료 중...")

    main_frame = _FindXshellMainFrame()
    if not main_frame:
        print("  [INFO] Xshell이 이미 종료됨")
        return

    win32gui.PostMessage(main_frame, win32con.WM_CLOSE, 0, 0)

    # 최대 3초 대기 + 잔여 팝업에 Enter 전송
    for _ in range(15):
        time.sleep(0.2)
        if not _FindXshellMainFrame():
            print("  [OK] Xshell 종료 완료")
            return
        # 혹시 남아있는 확인 다이얼로그 자동 처리
        pyautogui.press('enter')

    # 여전히 실행 중이면 강제 종료
    subprocess.run(
        ['taskkill', '/f', '/im', 'Xshell.exe'],
        capture_output=True, text=True,
    )
    time.sleep(1)
    print("  [OK] taskkill 강제 종료")


# ─── 화면 보호기 해제 ────────────────────────────────────────────────────────

def WakeScreen() -> None:
    """
    화면 보호기(비밀번호 없음)를 해제합니다.
    마우스를 1px 이동했다가 원위치 → Win32 mouse_event 신호로 보호기 해제.
    잠금 상태(비밀번호 있음)에는 효과 없으므로 오류를 무시합니다.
    """
    try:
        x, y = pyautogui.position()
        pyautogui.moveRel(1, 0, duration=0)
        time.sleep(0.1)
        pyautogui.moveRel(-1, 0, duration=0)
        pyautogui.moveTo(x, y, duration=0)
        print("  [OK] 화면 보호기 해제 신호 전송")
    except Exception as e:
        print(f"  [INFO] WakeScreen 건너뜀: {e}")
    time.sleep(0.5)


# ─── Main ─────────────────────────────────────────────────────────────────────

def Main() -> None:
    print("=" * 60)
    print("  Matgo Server Monitor")
    print("=" * 60)
    print()
    print("  !! 보안 주의 사항 !!")
    print("  - 서버 보안에 절대 주의")
    print("  - 서버 접속 후 관련 없는 작업 절대 불가")
    print("  - 서비스에 지장을 주는 행위 엄금")
    print("=" * 60)

    print("\n[Screen]")
    WakeScreen()

    if os.path.exists(DONE_FILE):
        os.remove(DONE_FILE)

    if not CheckPrerequisites():
        print("\n[ABORT] 필수 파일이 없습니다.")
        sys.exit(1)

    if not LaunchXshellAndRunScript():
        print("[ABORT] Xshell 스크립트 실행 실패.")
        sys.exit(1)

    if not WaitForDoneFile():
        print("[WARN] 타임아웃 - Xshell 스크립트 응답 없음")

    # _done.txt 감지 즉시 Xshell 종료 (MsgBox 없으므로 바로 닫기 가능)
    _CloseXshell()

    if os.path.exists(DONE_FILE):
        print("\n[Xshell 결과]")
        with open(DONE_FILE, encoding="utf-8") as f:
            for line in f:
                print(f"  {line.rstrip()}")

    print("\n" + "=" * 60)
    print(f"  출력 폴더: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    Main()
