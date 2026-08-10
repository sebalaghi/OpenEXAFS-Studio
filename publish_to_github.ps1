$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$bat = Join-Path $PSScriptRoot "PUBLISH_TO_GITHUB.bat"
if (-not (Test-Path $bat)) {
    throw "PUBLISH_TO_GITHUB.bat was not found."
}

$proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "`"$bat`"" -Wait -PassThru
exit $proc.ExitCode
