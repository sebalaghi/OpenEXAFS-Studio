@echo off
setlocal
cd /d "%~dp0"

echo OpenEXAFS Studio - Windows unblock helper
echo.
echo This removes the Windows "downloaded from the Internet" flag
echo from files in this extracted portable folder, then starts the app.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%~dp0' -Recurse -File | Unblock-File"

if errorlevel 1 (
  echo.
  echo Could not unblock all files.
  echo Right-click the original ZIP, choose Properties, tick Unblock, Apply,
  echo then extract it again to a new folder.
  pause
  exit /b 1
)

echo Starting OpenEXAFS Studio...
start "" "%~dp0OpenEXAFS-Studio.exe"
exit /b 0
