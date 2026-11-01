@echo off
rem Double-click entry point for start-stack.ps1 (operator side).
rem Extra arguments are passed through, e.g.  start-stack.cmd -Status
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-stack.ps1" %*
set "RC=%ERRORLEVEL%"
echo.
pause
exit /b %RC%
