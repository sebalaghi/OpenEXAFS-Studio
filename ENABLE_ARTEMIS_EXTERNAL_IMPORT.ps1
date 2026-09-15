param(
    [string]$ArtemisRoot = ""
)

$ErrorActionPreference = "Stop"

function Find-ArtemisFile {
    param([string]$RelativePath)

    $candidates = @()
    if ($ArtemisRoot) {
        $candidates += Join-Path $ArtemisRoot $RelativePath
    }

    $roots = @(
        "C:\Strawberry",
        "C:\Demeter",
        "C:\Program Files\Demeter",
        "C:\Program Files (x86)\Demeter",
        "$env:LOCALAPPDATA",
        "$env:APPDATA"
    ) | Where-Object { $_ -and (Test-Path $_) }

    foreach ($root in $roots) {
        try {
            $leaf = Split-Path $RelativePath -Leaf
            $hits = Get-ChildItem -Path $root -Filter $leaf -File -Recurse -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName.Replace("/", "\") -like "*$($RelativePath.Replace("/", "\"))*" }
            if ($hits) {
                $candidates += $hits.FullName
            }
        } catch {}
    }

    $candidate = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    return $candidate
}

Write-Host ""
Write-Host "OpenEXAFS Studio: enable Artemis external-FEFF importer" -ForegroundColor Cyan
Write-Host "Close Artemis before continuing." -ForegroundColor Yellow
Write-Host ""

$artemis = Find-ArtemisFile "Demeter\UI\Artemis.pm"
$import  = Find-ArtemisFile "Demeter\UI\Artemis\Import.pm"

if (-not $artemis) {
    throw "Could not locate Demeter\UI\Artemis.pm. Re-run with -ArtemisRoot pointing to the Perl library root or Demeter installation."
}
if (-not $import) {
    throw "Could not locate Demeter\UI\Artemis\Import.pm. Re-run with -ArtemisRoot pointing to the Perl library root or Demeter installation."
}

Write-Host "Artemis.pm: $artemis"
Write-Host "Import.pm:  $import"

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item $artemis "$artemis.openexafs_backup_$stamp" -Force
Copy-Item $import  "$import.openexafs_backup_$stamp" -Force

$artemisText = Get-Content $artemis -Raw
$oldMenu = '#$importmenu->Append($IMPORT_FEFF,     "an external Feff calculation",  "Import a Feff input file and the results of a calculation already made with that file");'
$newMenu = ' $importmenu->Append($IMPORT_FEFF,     "an external Feff calculation",  "Import a Feff input file and the results of a calculation already made with that file");'

if ($artemisText.Contains($oldMenu)) {
    $artemisText = $artemisText.Replace($oldMenu, $newMenu)
    Set-Content -Path $artemis -Value $artemisText -Encoding UTF8
    Write-Host "Enabled the external Feff calculation menu item." -ForegroundColor Green
} elseif ($artemisText.Contains('"an external Feff calculation"')) {
    Write-Host "External Feff menu entry already appears to be enabled." -ForegroundColor Green
} else {
    throw "Expected external-Feff menu line was not found in Artemis.pm. The installed Artemis source differs from Demeter 0.9.26."
}

$importText = Get-Content $import -Raw
$needle = '  my $efeff = Demeter::Feff::External -> new(screen=>0, name=>$filename);'
$replacement = '  eval "require Demeter::Feff::External";' + [Environment]::NewLine + $needle

if ($importText.Contains($needle) -and -not $importText.Contains('eval "require Demeter::Feff::External";' + [Environment]::NewLine + $needle)) {
    $importText = $importText.Replace($needle, $replacement)
    Set-Content -Path $import -Value $importText -Encoding UTF8
    Write-Host "Added the runtime load for Demeter::Feff::External." -ForegroundColor Green
} else {
    Write-Host "External module load is already present or this build loads it elsewhere." -ForegroundColor Green
}

Write-Host ""
Write-Host "Done. Restart Artemis." -ForegroundColor Cyan
Write-Host "Then use: File > Import... > an external Feff calculation" -ForegroundColor Cyan
Write-Host "Select the FEFF8 package's feff.inp and DO NOT click Run Feff." -ForegroundColor Yellow
Write-Host ""
