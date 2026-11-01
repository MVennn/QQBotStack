@echo off
rem QQBotStack one-click control menu (operator machine).
rem Reads target host/user from host\stack.conf at runtime - nothing machine
rem specific is hardcoded here. Double-click friendly; ASCII only.
setlocal
cd /d "%~dp0.."
set "H="
set "U="
for /f "tokens=2 delims==" %%a in ('findstr /b "host=" host\stack.conf 2^>nul') do set "H=%%a"
for /f "tokens=2 delims==" %%a in ('findstr /b "user=" host\stack.conf 2^>nul') do set "U=%%a"
if "%H%"=="" echo [x] host not found in host\stack.conf & pause & exit /b 2

:menu
cls
echo ================================================
echo   QQBotStack control      target: %U%@%H%
echo ================================================
echo   1. Status (services + ports + QQ login)
echo   2. Start missing services
echo   3. Restart AstrBot
echo   4. Restart wb2api gateway
echo   5. Restart zgate
echo   6. Open AstrBot panel (browser)
echo   7. Open wb2api panel (SSH tunnel :17863)
echo   8. Fetch NapCat QR code (scan to log in)
echo   9. SSH terminal to target
echo   0. Exit
echo.
set "c="
set /p c=Choose:
if not defined c exit /b 0
if "%c%"=="0" exit /b 0
if "%c%"=="1" powershell -NoProfile -ExecutionPolicy Bypass -File tools\start-stack.ps1 -Status
if "%c%"=="2" powershell -NoProfile -ExecutionPolicy Bypass -File tools\start-stack.ps1
if "%c%"=="3" powershell -NoProfile -ExecutionPolicy Bypass -File tools\start-stack.ps1 -Restart astrbot
if "%c%"=="4" powershell -NoProfile -ExecutionPolicy Bypass -File tools\start-stack.ps1 -Restart gateway
if "%c%"=="5" powershell -NoProfile -ExecutionPolicy Bypass -File tools\start-stack.ps1 -Restart zgate
if "%c%"=="6" start "" http://%H%:6185
if "%c%"=="7" call :tunnel
if "%c%"=="8" powershell -NoProfile -ExecutionPolicy Bypass -File tools\get-qr.ps1
if "%c%"=="9" ssh -t %U%@%H%
echo.
pause
goto menu

:tunnel
start "wb2api tunnel" /min cmd /c "ssh -N -L 17863:127.0.0.1:7863 %U%@%H%"
ping -n 3 127.0.0.1 >nul
start "" http://127.0.0.1:17863/panel/
echo tunnel window opened (minimize it to keep the panel working; close it when done)
exit /b 0
