@echo off
cd /d "D:\claude_work\matgo_server_report"
echo. >> log.txt
echo ===== %date% %time% 실행 시작 ===== >> log.txt
C:\Python314\python.exe main.py >> log.txt 2>&1
echo ===== 실행 완료 ===== >> log.txt
