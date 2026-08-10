$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$LogFile = Join-Path $PSScriptRoot "OpenEXAFS_install.log"
"OpenEXAFS Studio v0.1.4 install / repair / launch log" | Out-File $LogFile -Encoding utf8
("Started: " + (Get-Date).ToString("s")) | Out-File $LogFile -Append -Encoding utf8

function Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
    ("==> " + $Message) | Out-File $LogFile -Append -Encoding utf8
}

function Run-Native {
    param(
        [Parameter(Mandatory=$true)][string]$Exe,
        [Parameter(ValueFromRemainingArguments=$true)][string[]]$Args
    )
    ("RUN: " + $Exe + " " + ($Args -join " ")) | Out-File $LogFile -Append -Encoding utf8
    & $Exe @Args 2>&1 | Tee-Object -FilePath $LogFile -Append
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        throw "Command failed with exit code $code : $Exe $($Args -join ' ')"
    }
}

function Get-CandidatePrefixes {
    return @(
        (Join-Path $env:USERPROFILE "xraylarch"),
        (Join-Path $env:LOCALAPPDATA "xraylarch"),
        "C:\Users\Public\xraylarch"
    )
}

function Find-PythonPrefix {
    foreach ($prefix in Get-CandidatePrefixes) {
        $python = Join-Path $prefix "python.exe"
        if (Test-Path $python) {
            try {
                & $python -c "import sys; print(sys.executable)" *> $null
                if ($LASTEXITCODE -eq 0) {
                    return $prefix
                }
            } catch {}
        }
    }
    return $null
}

function Test-Larch([string]$Python) {
    if (-not (Test-Path $Python)) { return $false }
    try {
        & $Python -c "import larch, larixite; from larch.xafs import feffrunner, feffpath, feffit; print('Larch OK')" *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Repair-Larch([string]$Prefix) {
    $python = Join-Path $Prefix "python.exe"

    Step "Repairing the existing XrayLarch environment"
    Write-Host "Environment: $Prefix" -ForegroundColor Yellow
    Write-Host "Python:      $python" -ForegroundColor Yellow

    Run-Native $python -m ensurepip --upgrade
    Run-Native $python -m pip install --upgrade pip setuptools wheel

    # Official current XrayLarch packaging declares larixite as a core dependency.
    # The [larix] extra also installs the GUI/Jupyter dependencies used by Larix.
    Run-Native $python -m pip install --upgrade --no-cache-dir "xraylarch[larix]"

    Step "Verifying XrayLarch, Larixite and FEFFIT imports"
    Run-Native $python -c "import importlib.metadata as m; import larch, larixite; from larch.xafs import feffrunner, feffpath, feffit; from larch.utils import bindir; print('xraylarch =', m.version('xraylarch')); print('larixite =', m.version('larixite')); print('larch bindir =', bindir)"

    return $python
}

function Install-Fresh-Larch {
    $prefix = Join-Path $env:USERPROFILE "xraylarch"
    if ($prefix.Contains(" ")) { $prefix = "C:\Users\Public\xraylarch" }

    Step "No usable XrayLarch Python was found. Installing a fresh environment"
    Write-Host "Install location: $prefix" -ForegroundColor Yellow

    if (Test-Path $prefix) {
        $backup = $prefix + "_old_" + (Get-Date -Format "yyyyMMdd_HHmmss")
        Write-Host "Moving incomplete folder to: $backup" -ForegroundColor Yellow
        Move-Item -LiteralPath $prefix -Destination $backup -Force
    }

    $installer = Join-Path $env:TEMP "Miniforge3-Windows-x86_64.exe"
    $url = "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Windows-x86_64.exe"

    if (-not (Test-Path $installer)) {
        Step "Downloading Miniforge"
        Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    }

    Step "Installing Miniforge"
    $args = @("/InstallationType=JustMe", "/RegisterPython=0", "/S", "/D=$prefix")
    $proc = Start-Process -FilePath $installer -ArgumentList $args -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        throw "Miniforge installer failed with exit code $($proc.ExitCode)."
    }

    $conda = Join-Path $prefix "Scripts\conda.exe"
    $python = Join-Path $prefix "python.exe"
    if (-not (Test-Path $conda)) {
        throw "Conda was not found after Miniforge installation."
    }

    Step "Installing the scientific Python stack"
    Run-Native $conda install -y -c conda-forge `
        "python==3.13.10" `
        "numpy>=2.2.0" `
        "scipy>=1.15" `
        "matplotlib>=3.10" `
        "h5py>=3.13" `
        "mkl_fft" `
        "spglib>=2.7.0" `
        "pymatgen"

    # Install Larch exactly with the package extra recommended by its current docs.
    Step "Installing XrayLarch"
    Run-Native $python -m pip install --upgrade pip setuptools wheel
    Run-Native $python -m pip install --upgrade --no-cache-dir "xraylarch[larix]"

    return $python
}

try {
    Step "Checking for an existing XrayLarch / Miniforge Python"
    $prefix = Find-PythonPrefix

    if ($prefix) {
        $python = Join-Path $prefix "python.exe"
        if (Test-Larch $python) {
            Write-Host "Existing XrayLarch installation is healthy." -ForegroundColor Green
        } else {
            Write-Host "Python exists, but Larch/Larixite is missing or incomplete." -ForegroundColor Yellow
            $python = Repair-Larch $prefix
        }
    } else {
        $python = Install-Fresh-Larch
    }

    if (-not (Test-Larch $python)) {
        throw "XrayLarch repair/install finished but the import verification still failed."
    }

    Step "Installing OpenEXAFS Studio GUI dependency"
    Run-Native $python -m pip install --upgrade "PySide6>=6.7"

    Step "Installing OpenEXAFS Studio"
    Run-Native $python -m pip install --no-deps -e .

    Step "Running the focused startup diagnostic"
    Run-Native $python diagnose.py --smoke-test

    Step "Launching OpenEXAFS Studio"
    Write-Host "Dependencies are healthy. Opening the GUI..." -ForegroundColor Green
    & $python launch.py 2>&1 | Tee-Object -FilePath $LogFile -Append
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        throw "GUI exited with code $code. See OpenEXAFS_launch_error.log."
    }
    exit 0
}
catch {
    ""
    ("ERROR: " + $_.Exception.Message) | Tee-Object -FilePath $LogFile -Append
    Write-Host ""
    Write-Host "OpenEXAFS Studio did not start." -ForegroundColor Red
    Write-Host "Main log: $LogFile" -ForegroundColor Yellow
    Write-Host "Run DIAGNOSTIC.bat and send the diagnostic/install logs." -ForegroundColor Yellow
    exit 1
}
