@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Publish OpenEXAFS Studio to GitHub

echo.
echo ============================================================
echo OpenEXAFS Studio - GitHub publisher v0.2.1
echo ============================================================
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo ERROR: Git for Windows is not installed or not on PATH.
  echo Install Git for Windows, then run this file again.
  goto :FAIL
)

where gh >nul 2>&1
if errorlevel 1 (
  echo ERROR: GitHub CLI ^(gh^) is not installed or not on PATH.
  echo Install GitHub CLI, then run this file again.
  goto :FAIL
)

echo [1/8] Checking GitHub authentication...
gh auth status >nul 2>&1
if errorlevel 1 (
  echo GitHub login is required. Opening GitHub CLI login...
  gh auth login
  if errorlevel 1 goto :FAIL
)

for /f "usebackq delims=" %%U in (`gh api user --jq ".login"`) do set "GHUSER=%%U"
for /f "usebackq delims=" %%I in (`gh api user --jq ".id"`) do set "GHID=%%I"

if not defined GHUSER (
  echo ERROR: Could not determine the authenticated GitHub username.
  goto :FAIL
)

set "REPONAME=OpenEXAFS-Studio"
set "REPO=%GHUSER%/%REPONAME%"
set "REMOTEURL=https://github.com/%REPO%.git"
set "PAGESURL=https://%GHUSER%.github.io/%REPONAME%/"

echo       Account: %GHUSER%
echo       Target:  %REPO%
echo.

echo [2/8] Preparing local Git repository...
if not exist ".git" (
  git init
  if errorlevel 1 goto :FAIL
)

git branch -M main
if errorlevel 1 goto :FAIL

REM Configure a repository-local identity only when none is available.
git config user.name >nul 2>&1
if errorlevel 1 (
  git config user.name "%GHUSER%"
  if errorlevel 1 goto :FAIL
)

git config user.email >nul 2>&1
if errorlevel 1 (
  if defined GHID (
    git config user.email "%GHID%+%GHUSER%@users.noreply.github.com"
  ) else (
    git config user.email "%GHUSER%@users.noreply.github.com"
  )
  if errorlevel 1 goto :FAIL
)

echo [3/8] Creating / updating local commit...
git add .
if errorlevel 1 goto :FAIL

git diff --cached --quiet
if errorlevel 1 (
  git commit -m "OpenEXAFS Studio v0.2.1"
  if errorlevel 1 goto :FAIL
) else (
  echo       No new local changes to commit.
)

echo [4/8] Checking whether the GitHub repository already exists...
gh repo view "%REPO%" --json name >nul 2>&1
if errorlevel 1 goto :CREATE_REPO

echo       Repository already exists.
goto :PUSH_EXISTING

:CREATE_REPO
echo       Repository does not exist yet. Creating it now...
REM gh repo create supports OWNER/REPO, --source, --remote, and --push.
gh repo create "%REPO%" --public --source=. --remote=origin --push --description "Open-source EXAFS GUI using XrayLarch and Feff8L"
if errorlevel 1 (
  echo.
  echo ERROR: GitHub repository creation failed.
  echo Check the message above and your GitHub CLI permissions.
  goto :FAIL
)
goto :AFTER_PUSH

:PUSH_EXISTING
echo [5/8] Configuring origin and pushing main...
git remote get-url origin >nul 2>&1
if errorlevel 1 (
  git remote add origin "%REMOTEURL%"
  if errorlevel 1 goto :FAIL
) else (
  git remote set-url origin "%REMOTEURL%"
  if errorlevel 1 goto :FAIL
)

git push -u origin main
if errorlevel 1 goto :FAIL
goto :AFTER_PUSH

:AFTER_PUSH
echo.
echo [5/8] Repository published successfully:
echo       https://github.com/%REPO%
echo.

echo [6/8] Enabling GitHub Pages with GitHub Actions...
gh api "repos/%REPO%/pages" >nul 2>&1
if errorlevel 1 (
  gh api -X POST "repos/%REPO%/pages" -f build_type=workflow >nul 2>&1
  if errorlevel 1 (
    echo       Pages could not be enabled automatically.
    echo       The repository itself is already published.
    echo       You can enable Pages later from GitHub Settings ^> Pages ^> GitHub Actions.
    set "PAGES_ENABLED=0"
  ) else (
    echo       GitHub Pages enabled.
    set "PAGES_ENABLED=1"
  )
) else (
  echo       GitHub Pages is already enabled.
  set "PAGES_ENABLED=1"
)

echo [7/8] Triggering the Pages workflow...
if "%PAGES_ENABLED%"=="1" (
  set "WORKFLOW_OK=0"
  for /L %%N in (1,1,5) do (
    if "!WORKFLOW_OK!"=="0" (
      gh workflow run pages.yml --repo "%REPO%" --ref main >nul 2>&1
      if not errorlevel 1 (
        set "WORKFLOW_OK=1"
      ) else (
        if not "%%N"=="5" (
          echo       Workflow not visible yet. Retrying in 3 seconds...
          timeout /t 3 /nobreak >nul
        )
      )
    )
  )

  if "!WORKFLOW_OK!"=="1" (
    echo       Pages deployment workflow triggered.
  ) else (
    echo       Could not manually trigger Pages yet.
    echo       The workflow also runs automatically on pushes to main.
  )
) else (
  echo       Skipping workflow trigger because Pages is not enabled.
)

echo [8/8] Opening GitHub...
start "" "https://github.com/%REPO%"
start "" "https://github.com/%REPO%/actions"

echo.
echo ============================================================
echo SUCCESS
echo.
echo Repository:
echo   https://github.com/%REPO%
echo.
echo GitHub Pages:
echo   %PAGESURL%
echo.
echo The Pages site can take a minute or two to become available.
echo ============================================================
echo.
pause
exit /b 0

:FAIL
echo.
echo ============================================================
echo Publishing did not complete.
echo.
echo IMPORTANT:
echo The old publisher incorrectly treated a failed "gh repo view" as if
echo the repository existed, then tried to use a missing "origin" remote.
echo This v0.2.1 publisher checks native command exit codes directly.
echo ============================================================
echo.
pause
exit /b 1
