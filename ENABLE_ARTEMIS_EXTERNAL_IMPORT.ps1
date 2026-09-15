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
$external = Find-ArtemisFile "Demeter\Feff\External.pm"

if (-not $artemis) {
    throw "Could not locate Demeter\UI\Artemis.pm. Re-run with -ArtemisRoot pointing to the Perl library root or Demeter installation."
}
if (-not $import) {
    throw "Could not locate Demeter\UI\Artemis\Import.pm. Re-run with -ArtemisRoot pointing to the Perl library root or Demeter installation."
}
if (-not $external) {
    throw "Could not locate Demeter\Feff\External.pm. Re-run with -ArtemisRoot pointing to the Perl library root or Demeter installation."
}

Write-Host "Artemis.pm: $artemis"
Write-Host "Import.pm:  $import"
Write-Host "External.pm: $external"

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item $artemis "$artemis.openexafs_backup_$stamp" -Force
Copy-Item $import  "$import.openexafs_backup_$stamp" -Force
Copy-Item $external "$external.openexafs_backup_$stamp" -Force

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

# Demeter 0.9.26 creates the external Feff object and description page, but its
# _external_feff() routine does not populate the Paths table.  The same
# fill_ss_page() call is used elsewhere in Artemis after restoring/importing Feff.
$importText = Get-Content $import -Raw
$fillNeedle = '  $rframes->{$fnum}->{Feff}->fill_intrp_page($efeff);'
$fillLine   = '  $rframes->{$fnum}->{Feff}->fill_ss_page($efeff);'
if ($importText.Contains($fillNeedle) -and -not $importText.Contains($fillNeedle + [Environment]::NewLine + $fillLine)) {
    $importText = $importText.Replace(
        $fillNeedle,
        $fillNeedle + [Environment]::NewLine + $fillLine
    )
    Set-Content -Path $import -Value $importText -Encoding UTF8
    Write-Host "Enabled population of the Artemis Paths table for external Feff calculations." -ForegroundColor Green
} elseif ($importText.Contains($fillLine)) {
    Write-Host "External Feff Paths-table population patch is already present." -ForegroundColor Green
} else {
    throw "Could not locate the external-Feff fill_intrp_page() call in Import.pm."
}

$externalText = Get-Content $external -Raw
$oldComplete = @'
  return ( $self->npaths
	   and $self->filesdat and (-e $self->filesdat) and (-r $self->filesdat)
	   and $self->phasebin and (-e $self->phasebin) and (-r $self->phasebin)
	 );
'@
$newComplete = @'
  # OpenEXAFS Studio compatibility: current Feff8L path calculations may not
  # produce the legacy phase.bin file.  Artemis fitting uses the imported
  # feffNNNN.dat scattering-path files, so require those plus files.dat.
  return ( $self->npaths
	   and $self->filesdat and (-e $self->filesdat) and (-r $self->filesdat)
	 );
'@

if ($externalText.Contains($oldComplete)) {
    $externalText = $externalText.Replace($oldComplete, $newComplete)
    Set-Content -Path $external -Value $externalText -Encoding UTF8
    Write-Host "Relaxed legacy phase.bin requirement for Feff8L external paths." -ForegroundColor Green
} elseif ($externalText.Contains("OpenEXAFS Studio compatibility")) {
    Write-Host "Feff8L phase.bin compatibility patch is already present." -ForegroundColor Green
} else {
    throw "Expected is_complete() block was not found in External.pm. The installed Demeter source differs from 0.9.26."
}

Write-Host ""
Write-Host "Done. Restart Artemis." -ForegroundColor Cyan
Write-Host "Then use: File > Import... > an external Feff calculation" -ForegroundColor Cyan
Write-Host "Select the FEFF8 package's feff.inp and DO NOT click Run Feff." -ForegroundColor Yellow
Write-Host ""
