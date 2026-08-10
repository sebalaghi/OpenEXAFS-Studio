@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title OpenEXAFS Studio


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

"%PY%" -u -c "import larch, larixite; from larch.xafs import feffit" >nul 2>&1
if errorlevel 1 (
  echo XrayLarch is incomplete. Starting repair...
  call "%~dp0REPAIR_AND_RUN.bat"
  exit /b %ERRORLEVEL%
)

"%PY%" -u launch.py
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo GUI launch failed. See OpenEXAFS_launch_error.log
  echo.
  pause
)
exit /b %RC%
