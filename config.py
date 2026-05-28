"""
맞고 서버 모니터링 자동화 설정 파일
- 세션 경로, 타임아웃, 저장 경로 등 모든 설정값을 관리합니다.
"""

import os

# ─── Xshell 실행 파일 경로 ───────────────────────────────────────────────────
XSHELL_EXE: str = r"C:\Program Files (x86)\NetSarang\Xshell 8\Xshell.exe"

# ─── Xshell 세션 파일 경로 ───────────────────────────────────────────────────
SESSION_BASE: str = os.path.join(
    os.environ["USERPROFILE"],
    "Documents",
    "NetSarang Computer",
    "8",
    "Xshell",
    "Sessions",
    "CW_MATGO_REAL",
)

SESSIONS: list[dict] = [
    {
        "name": "cw_real_game_1",
        "path": os.path.join(SESSION_BASE, "cw_real_game_1.xsh"),
    },
    {
        "name": "cw_real_game_2",
        "path": os.path.join(SESSION_BASE, "cw_real_game_2.xsh"),
    },
    {
        "name": "cw_real_game_3",
        "path": os.path.join(SESSION_BASE, "cw_real_game_3.xsh"),
    },
]

# ─── 출력 및 스크립트 경로 ───────────────────────────────────────────────────
OUTPUT_DIR: str = r"D:\claude_work\matgo_server_report\file"
XSHELL_SCRIPT: str = r"D:\claude_work\matgo_server_report\xshell_script.py"
PYTHON_EXE: str = r"C:\Python314\python.exe"

# ─── 타임아웃 설정 (밀리초) ──────────────────────────────────────────────────
SSH_CONNECT_TIMEOUT_MS: int = 10000  # SSH 접속 완료까지 대기 시간
PM2_WAIT_MS: int = 4000              # pm2 ls 결과 완료까지 대기 시간
SESSION_CLOSE_WAIT_MS: int = 1000   # 세션 닫기 후 안정화 대기 시간

# ─── 파일명 타임스탬프 형식 ──────────────────────────────────────────────────
# 결과: "2026-05-27 16-20_cw_real_game.txt"
TIMESTAMP_FORMAT: str = "%Y-%m-%d %H-%M"  # ':' is forbidden in Windows filenames
