@echo off
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\start_pelagos.py"
if errorlevel 1 pause
