@echo off
cd /d "D:\claude_work\matgo_server_report"
echo START >> log.txt
C:\Python314\python.exe "D:\claude_work\matgo_server_report\main.py" >> log.txt 2>&1
echo END >> log.txt
