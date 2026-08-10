@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title OpenEXAFS Studio Diagnostic v0.1.6


set "PREFIX=%USERPROFILE%\xraylarch"
set "PY=%PREFIX%\python.exe"
set "ACTIVATE=%PREFIX%\Scripts\activate.bat"

if not exist "%PY%" (
  echo XrayLarch runtime not found at:
  echo   %PY%
  echo Run INSTALL_AND_RUN.bat first.
  echo.
  pause
  exit /b 1
)

REM Activate the Miniforge base environment so DLL/path discovery sees a real
REM active conda environment instead of "No conda env active, defaulting to base".
if exist "%ACTIVATE%" (
  call "%ACTIVATE%" "%PREFIX%"
) else (
  set "CONDA_PREFIX=%PREFIX%"
  set "CONDA_DEFAULT_ENV=base"
  set "CONDA_SHLVL=1"
  set "PATH=%PREFIX%;%PREFIX%\Library\bin;%PREFIX%\Scripts;%PREFIX%\condabin;%PATH%"
)

echo Diagnostic interpreter:
echo   %PY%
echo Active conda prefix:
echo   %CONDA_PREFIX%
echo.

"%PY%" -u diagnose.py --smoke-test
set "RC=%ERRORLEVEL%"

echo.
echo Diagnostic log:
echo   %~dp0OpenEXAFS_diagnostic.log
echo.
pause
exit /b %RC%
