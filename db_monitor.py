"""
맞고 서버 DB 모니터링
ADMIN_STATISTICS_BUY 테이블의 전일 포인트 통계를 수집하여
오늘 날짜의 file/*_cw_real_game.txt 파일에 추가합니다.

!! 보안 주의 사항 !!
  - DB 데이터 수정/삭제/추가 일체 금지 (SELECT 전용)
  - DB 접속 정보는 _db_cred.ini 에서 읽음 (코드에 직접 기재 금지)
  - _db_cred.ini 는 git에 포함되지 않음

실행 방법:
  C:\\Python314\\python.exe db_monitor.py
"""

import configparser
import glob
import os
import sys
from datetime import datetime

_BASE_DIR  = r"D:\claude_work\matgo_server_report"
_CRED_FILE = os.path.join(_BASE_DIR, "_db_cred.ini")
_LOG_FILE  = os.path.join(_BASE_DIR, "log.txt")   # 오류 기록용 fallback

# READ ONLY — 수정/삭제/추가 쿼리 절대 금지
_QUERY = (
    "SELECT TO_CHAR(reg_date, 'YYYY-MM-DD') AS reg_date, "
    "       point_total "
    "FROM   GAMEN.ADMIN_STATISTICS_BUY "
    "WHERE  TRUNC(reg_date) = TRUNC(SYSDATE) - 1 "
    "ORDER  BY reg_date DESC"
)


def FindTodayOutputFile():
    """오늘 날짜의 file/*_cw_real_game.txt 중 가장 최근 파일을 반환합니다."""
    today   = datetime.now().strftime("%Y-%m-%d")
    pattern = os.path.join(_BASE_DIR, "file", f"{today}*_cw_real_game.txt")
    files   = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def LoadCredentials():
    if not os.path.exists(_CRED_FILE):
        sys.exit(
            f"[ERROR] 접속 정보 파일 없음: {_CRED_FILE}\n"
            "  _db_cred.ini.template 을 복사 후 실제 접속 정보를 입력하세요."
        )
    cfg = configparser.ConfigParser()
    cfg.read(_CRED_FILE, encoding="utf-8")
    sec = "cashwalk_real"
    if sec not in cfg:
        sys.exit(f"[ERROR] _db_cred.ini 에 [{sec}] 섹션이 없습니다.")
    return dict(cfg[sec])


def QueryStats(cred):
    import oracledb  # 런타임에 import — 미설치 시 명확한 오류 메시지 출력

    # SID 방식 DSN (connections.json 에서 사용하는 방식과 동일)
    dsn = (
        f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)"
        f"(HOST={cred['host']})(PORT={cred['port']}))"
        f"(CONNECT_DATA=(SID={cred['sid']})))"
    )
    with oracledb.connect(user=cred["user"], password=cred["password"], dsn=dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(_QUERY)
            return cur.fetchall()


def AppendToOutputFile(rows, target_path):
    """pm2 결과 파일 끝에 DB 통계 섹션을 추가합니다."""
    thick = "=" * 64
    thin  = "-" * 64

    lines = [
        "",
        "[DB]  ADMIN_STATISTICS_BUY  전일 포인트 통계",
        thin,
    ]

    if rows:
        lines.append(f"  {'reg_date':<12}  {'point_total':>15}")
        lines.append(thin)
        for reg_date, point_total in rows:
            pt = int(point_total) if point_total is not None else 0
            lines.append(f"  {reg_date:<12}  {pt:>15,}")
    else:
        lines.append("  (전일 데이터 없음)")

    lines += [thick, ""]

    body = "\n".join(lines) + "\n"
    with open(target_path, "a", encoding="utf-8") as f:
        f.write(body)

    print(body, end="")


def Main():
    print("=" * 60)
    print("  Matgo DB Monitor")
    print("  !! DB 데이터 수정/삭제/추가 일체 금지 !!")
    print("=" * 60)

    try:
        target = FindTodayOutputFile()
        if target:
            print(f"  저장 대상: {target}")
        else:
            print("[WARN] 오늘 날짜의 cw_real_game 파일 없음 → log.txt 에 기록합니다.")
            target = _LOG_FILE

        cred = LoadCredentials()
        print(f"  접속 시도: {cred['host']}:{cred['port']}/{cred['sid']}")

        rows = QueryStats(cred)
        print(f"  조회 완료: {len(rows)}건")

        AppendToOutputFile(rows, target)
        print(f"  기록 완료: {target}")

    except ImportError:
        msg = "[ERROR] oracledb 미설치\n  C:\\Python314\\python.exe -m pip install oracledb"
        _WriteErrorLog(msg)
        sys.exit(msg)
    except Exception as e:
        msg = f"[ERROR] {e}"
        _WriteErrorLog(str(e))
        sys.exit(msg)


def _WriteErrorLog(detail):
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"DB_ERROR {now}: {detail}\n"
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


if __name__ == "__main__":
    Main()
