@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if "%~1"=="" if exist "Lean Plan.exe" (
  start "" /d "%~dp0" "%~dp0Lean Plan.exe"
  exit /b 0
)
if exist ".runtime\python.exe" (
  ".runtime\python.exe" "app.py" %*
  if errorlevel 1 pause
  exit /b
)
echo The bundled Python runtime is missing.
echo Keep the entire Leanapp folder together when moving the app.
echo If you have Python 3.11 or newer, run: python app.py
pause
