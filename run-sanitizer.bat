@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" /B ".venv\Scripts\pythonw.exe" -m src.main %*
    exit /b 0
)

where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" /B pyw -3 -m src.main %*
    exit /b 0
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" /B pythonw -m src.main %*
    exit /b 0
)

where python >nul 2>nul
if %errorlevel%==0 (
    python -m src.main %*
    exit /b %errorlevel%
)

echo [ERROR] Python 3.11+ was not found. Install from https://www.python.org/downloads/
echo         or create .venv and install requirements.txt first.
pause
exit /b 1
