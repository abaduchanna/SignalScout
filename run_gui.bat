@echo off
rem SignalScout - run from source (fallback when antivirus quarantines a built exe)
rem Developed by www.3SVerse.com
setlocal
cd /d "%~dp0"
where py >nul 2>nul && (py -3 -m venv .venv) || (python -m venv .venv)
call .venv\Scripts\activate.bat
python -m pip install -e . -q
python run_gui.py
endlocal
