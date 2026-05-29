@echo off
cd /d "D:\claude_work\matgo_server_report"
echo DB_START >> log.txt
C:\Python314\python.exe "D:\claude_work\matgo_server_report\db_monitor.py" >> log.txt 2>&1
echo DB_END >> log.txt
