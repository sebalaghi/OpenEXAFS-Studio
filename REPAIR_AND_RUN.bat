@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title OpenEXAFS Studio Repair v0.1.6

set "LOG=%~dp0OpenEXAFS_install.log"
> "%LOG%" echo OpenEXAFS Studio v0.1.6 install / repair log
>>"%LOG%" echo Started: %DATE% %TIME%
>>"%LOG%" echo Project: %CD%

echo.
echo ============================================================
echo OpenEXAFS Studio v0.1.6
echo XrayLarch installer / repair + activated runtime
echo ============================================================
echo.

set "PREFIX=%USERPROFILE%\xraylarch"
set "PY=%PREFIX%\python.exe"
set "ACTIVATE=%PREFIX%\Scripts\activate.bat"

REM ------------------------------------------------------------
REM 1. Install Miniforge only if the dedicated Python does not exist.
REM ------------------------------------------------------------
if exist "%PY%" goto :ACTIVATE_ENV

echo [1/8] Installing the dedicated Miniforge/XrayLarch runtime...
>>"%LOG%" echo [1/8] Installing Miniforge

set "MINIFORGE=%TEMP%\Miniforge3-Windows-x86_64.exe"
if not exist "%MINIFORGE%" (
    echo Downloading Miniforge...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Windows-x86_64.exe' -OutFile '%MINIFORGE%'" >>"%LOG%" 2>&1
    if errorlevel 1 goto :FAIL
)

if exist "%PREFIX%" (
    echo Removing incomplete folder: %PREFIX%
    rmdir /s /q "%PREFIX%" >>"%LOG%" 2>&1
    if exist "%PREFIX%" goto :FAIL
)

"%MINIFORGE%" /InstallationType=JustMe /RegisterPython=0 /S /D=%PREFIX% >>"%LOG%" 2>&1
if errorlevel 1 goto :FAIL
if not exist "%PY%" goto :FAIL

:ACTIVATE_ENV
echo [1/8] Runtime found:
echo       %PY%

REM ------------------------------------------------------------
REM 2. ACTIVATE the Miniforge environment. This is the key v0.1.6 fix.
REM ------------------------------------------------------------
echo.
echo [2/8] Activating the XrayLarch Miniforge environment...
if exist "%ACTIVATE%" (
    call "%ACTIVATE%" "%PREFIX%"
    if errorlevel 1 goto :FAIL
) else (
    set "CONDA_PREFIX=%PREFIX%"
    set "CONDA_DEFAULT_ENV=base"
    set "CONDA_SHLVL=1"
    set "PATH=%PREFIX%;%PREFIX%\Library\bin;%PREFIX%\Scripts;%PREFIX%\condabin;%PATH%"
)
echo       CONDA_PREFIX=%CONDA_PREFIX%
>>"%LOG%" echo CONDA_PREFIX=%CONDA_PREFIX%
>>"%LOG%" echo PATH=%PATH%

REM ------------------------------------------------------------
REM 3. pip
REM ------------------------------------------------------------
echo.
echo [3/8] Preparing pip...
"%PY%" -m ensurepip --upgrade >>"%LOG%" 2>&1
"%PY%" -m pip install --upgrade pip setuptools wheel >>"%LOG%" 2>&1
if errorlevel 1 goto :FAIL

REM ------------------------------------------------------------
REM 4. XrayLarch
REM ------------------------------------------------------------
echo.
echo [4/8] Installing / repairing XrayLarch + Larixite...
echo       This can take several minutes on the first run.
"%PY%" -m pip install --upgrade --no-cache-dir "xraylarch[larix]" >>"%LOG%" 2>&1
if errorlevel 1 goto :FAIL
"%PY%" -m pip install --upgrade --no-cache-dir larixite pymatgen >>"%LOG%" 2>&1
if errorlevel 1 goto :FAIL

REM ------------------------------------------------------------
REM 5. Immediate import verification with unbuffered Python.
REM ------------------------------------------------------------
echo.
echo [5/8] Verifying XrayLarch imports...
"%PY%" -u -c "import sys; print('Python:',sys.executable,flush=True); import larch; print('larch OK',flush=True); import larixite; print('larixite OK',flush=True); from larch.xafs import feffrunner,feffpath,feffit; print('FEFF tools OK',flush=True); from larch.xrd.structure2feff import structure2feffinp; print('Structure-to-FEFF OK',flush=True)"
if errorlevel 1 goto :FAIL

REM ------------------------------------------------------------
REM 6. GUI deps / OpenEXAFS
REM ------------------------------------------------------------
echo.
echo [6/8] Installing GUI dependencies and OpenEXAFS Studio...
"%PY%" -m pip install --upgrade "PySide6>=6.7" matplotlib numpy scipy >>"%LOG%" 2>&1
if errorlevel 1 goto :FAIL
"%PY%" -m pip install --no-deps -e . >>"%LOG%" 2>&1
if errorlevel 1 goto :FAIL

REM ------------------------------------------------------------
REM 7. Diagnostic
REM ------------------------------------------------------------
echo.
echo [7/8] Running live diagnostic...
"%PY%" -u diagnose.py --smoke-test
if errorlevel 1 goto :FAIL

REM ------------------------------------------------------------
REM 8. Launch
REM ------------------------------------------------------------
echo.
echo [8/8] Launching OpenEXAFS Studio...
"%PY%" -u launch.py
if errorlevel 1 goto :FAIL

exit /b 0

:FAIL
echo.
echo ============================================================
echo OpenEXAFS Studio installation / repair FAILED.
echo.
echo Please send:
echo   %LOG%
echo   %~dp0OpenEXAFS_diagnostic.log   ^(if present^)
echo   %~dp0OpenEXAFS_launch_error.log ^(if present^)
echo ============================================================
echo.
pause
exit /b 1
