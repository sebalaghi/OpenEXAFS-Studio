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

# Demeter 0.9.26's normal fill_intrp_page() ranks paths and can call FEFF again.
# For an external Feff8L calculation we must not do that.  Instead, populate the
# visible Artemis Paths list directly from the ScatteringPath objects already
# created from feffNNNN.dat by Demeter::Feff::External.
$importText = Get-Content $import -Raw

$oldFill = '  $rframes->{$fnum}->{Feff}->fill_intrp_page($efeff);'
$newFill = @'
  # OpenEXAFS Studio: show externally generated Feff8L paths without ranking
  # or rerunning FEFF.  Demeter::Feff::External has already parsed each
  # feffNNNN.dat into a ScatteringPath object at this point.
  if (ref($efeff) =~ m{External}) {
    $rframes->{$fnum}->make_page('Paths') if not $rframes->{$fnum}->{Paths};
    $rframes->{$fnum}->{Paths}->{name}->SetValue($efeff->name);
    $rframes->{$fnum}->{Paths}->{header}->SetValue($efeff->intrp_header);
    my $plist = $rframes->{$fnum}->{Paths}->{paths};
    $plist->DeleteAllItems;
    my $i = 1;
    foreach my $p (@{$efeff->pathlist}) {
      $p->pathfinder_index($i);
      my $idx = $plist->InsertImageStringItem($i, sprintf("%3d", $i), 0);
      $plist->SetItemData($idx, $i);
      $plist->SetItem($idx, 1, sprintf("%.2f", $p->n));
      $plist->SetItem($idx, 2, sprintf("%.3f", $p->fuzzy));
      $plist->SetItem($idx, 3, $p->intrplist);
      $plist->SetItem($idx, 4, q{external});
      $plist->SetItem($idx, 5, $p->nleg);
      $plist->SetItem($idx, 6, $p->Type);
      ++$i;
    }
  } else {
    $rframes->{$fnum}->{Feff}->fill_intrp_page($efeff);
  };
'@

if ($importText.Contains($oldFill)) {
    # Remove any previous OpenEXAFS fill_ss_page line that may have been added.
    $importText = $importText.Replace(
        $oldFill + [Environment]::NewLine + '  $rframes->{$fnum}->{Feff}->fill_ss_page($efeff);',
        $oldFill
    )
    # Replace only the occurrence inside _external_feff by using the last occurrence.
    $pos = $importText.LastIndexOf($oldFill)
    if ($pos -lt 0) { throw "Could not locate external fill_intrp_page() call." }
    $importText = $importText.Substring(0, $pos) + $newFill + $importText.Substring($pos + $oldFill.Length)
    Set-Content -Path $import -Value $importText -Encoding UTF8
    Write-Host "Patched external FEFF import to populate the Paths table directly from feffNNNN.dat." -ForegroundColor Green
} elseif ($importText.Contains("OpenEXAFS Studio: show externally generated Feff8L paths")) {
    Write-Host "External FEFF8 Paths-table patch is already present." -ForegroundColor Green
} else {
    throw "Could not locate the external fill_intrp_page() call in Import.pm."
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
