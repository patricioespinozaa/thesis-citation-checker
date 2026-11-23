@echo off
cd /d "%~dp0"
where python >nul 2>nul && (python scripts\viewer.py) || (py scripts\viewer.py)
pause
