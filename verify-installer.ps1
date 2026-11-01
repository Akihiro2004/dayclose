$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$releaseVersion = python -c 'from version import APP_VERSION; print(APP_VERSION)'
if ($LASTEXITCODE -ne 0) { throw 'Could not read app version' }
$registry = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{20E87304-B8CB-46D9-957D-CF5A88A972F9}_is1'
$appPaths = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\Dayclose.exe'
if ((Test-Path $registry) -or (Test-Path $appPaths)) {
    throw 'An installed copy already exists. Installer verification will not replace it.'
}
$testRoot = Join-Path $PSScriptRoot ('build\installer-check-' + [guid]::NewGuid().ToString('N'))
$target = Join-Path $testRoot 'app'
$groupName = 'Dayclose Packaging Check'
$group = Join-Path ([Environment]::GetFolderPath('Programs')) $groupName
if (Test-Path -LiteralPath $group) { throw 'Test Start menu group already exists.' }
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$installer = Join-Path $PSScriptRoot "release\Dayclose-Setup-$releaseVersion.exe"
$installed = $false
try {
    $arguments = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /TASKS="" /DIR="{0}" /GROUP="{1}" /LOG="{2}"' -f $target, $groupName, (Join-Path $testRoot 'install.log')
    $setup = Start-Process -FilePath $installer -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
    if ($setup.ExitCode -ne 0) { throw "Installer returned $($setup.ExitCode)." }
    $installed = $true
    $exe = Join-Path $target 'Dayclose.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw 'Installed executable missing.' }
    $entry = Get-ItemProperty $registry
    if ($entry.DisplayName -ne 'Dayclose' -or $entry.DisplayVersion -ne $releaseVersion) { throw 'Installed apps metadata mismatch.' }
    $version = (Get-Item -LiteralPath $exe).VersionInfo
    if ($version.ProductName -ne 'Dayclose' -or $version.FileVersion -ne $releaseVersion) { throw 'Executable metadata mismatch.' }
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut((Join-Path $group 'Review & Shut Down.lnk'))
    if ($link.TargetPath -ne $exe -or $link.Arguments -ne '--shutdown') { throw 'Shutdown shortcut mismatch.' }
    $testData = Join-Path $testRoot 'data'
    $launchArgs = '--shutdown --dry-run --data-dir="{0}"' -f $testData
    $launch = Start-Process -FilePath $exe -ArgumentList $launchArgs -PassThru
    $windowFound = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        $ownedProcesses = Get-Process Dayclose -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe }
        if ($ownedProcesses | Where-Object { $_.MainWindowTitle -eq 'Dayclose · Shutdown review' }) {
            $windowFound = $true
            break
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $windowFound) { throw 'Packaged shutdown review did not open.' }
    $database = Join-Path $testData 'reminders.db'
    if (-not (Test-Path -LiteralPath $database)) { throw 'Packaged app did not initialize its database.' }
    $env:DAYCLOSE_TEST_DB = $database
    python -c 'import os,sqlite3; c=sqlite3.connect(os.environ["DAYCLOSE_TEST_DB"]); c.execute("INSERT INTO reminders(title,notes,status,start,end,all_day) VALUES (?,?,?,?,?,?)", ("Update test", "Keep this reminder", "Active", "22:00", "02:00", 0)); c.commit(); c.close()'
    if ($LASTEXITCODE -ne 0) { throw 'Could not seed test reminder' }
    $settingsPath = Join-Path $testData 'appearance.ini'
    '[General]', 'appearance=Dark', 'sort_order=Newest first', 'default_filter=All statuses', 'show_preview=true' | Set-Content -LiteralPath $settingsPath -Encoding ascii
    $settingsHash = (Get-FileHash -LiteralPath $settingsPath).Hash
    $helperPath = Join-Path $PSScriptRoot 'build\Dayclose.UpdateHelper.exe'
    $digest = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
    $reviewProcess = $ownedProcesses | Where-Object { $_.MainWindowTitle -eq 'Dayclose · Shutdown review' } | Select-Object -First 1
    $helperArgs = '"{0}" {1} "{2}" "{3}" {4} {5} true' -f $installer, $digest, $target, $testData, $reviewProcess.Id, $releaseVersion
    $helper = Start-Process -FilePath $helperPath -ArgumentList $helperArgs -WindowStyle Hidden -PassThru
    # These processes belong exclusively to the fresh test installation.
    Get-Process Dayclose -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe } | Stop-Process -Force
    if (-not $helper.WaitForExit(60000)) { throw 'Update helper did not complete in 60 seconds.' }
    if ($helper.ExitCode -ne 0) { throw 'Update helper failed.' }
    $restarted = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        $running = Get-Process Dayclose -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe }
        if ($running | Where-Object { $_.MainWindowTitle -eq 'Dayclose · Reminders' }) { $restarted = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $restarted) { throw 'Dayclose did not automatically reopen after updating.' }
    if ((Get-FileHash -LiteralPath $settingsPath).Hash -ne $settingsHash) { throw 'Update changed saved preferences.' }
    python -c 'import os,sqlite3; c=sqlite3.connect(os.environ["DAYCLOSE_TEST_DB"]); assert c.execute("SELECT title,notes,start,end FROM reminders").fetchone() == ("Update test", "Keep this reminder", "22:00", "02:00"); c.close()'
    if ($LASTEXITCODE -ne 0) { throw 'Update did not preserve reminder contents.' }
    Get-Process Dayclose -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe } | Stop-Process -Force
    Start-Sleep -Milliseconds 500
    $uninstaller = Join-Path $target 'unins000.exe'
    # The uninstaller is only allowed to target the fresh test directory in this workspace.
    $resolvedTarget = [IO.Path]::GetFullPath($target)
    $workspaceBuild = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'build')) + [IO.Path]::DirectorySeparatorChar
    if (-not $resolvedTarget.StartsWith($workspaceBuild, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected uninstall target.' }
    $uninstall = Start-Process -FilePath $uninstaller -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART' -WindowStyle Hidden -Wait -PassThru
    if ($uninstall.ExitCode -ne 0) { throw "Uninstaller returned $($uninstall.ExitCode)." }
    if ((Test-Path $registry) -or (Test-Path $appPaths) -or (Test-Path -LiteralPath $exe) -or (Test-Path -LiteralPath $group)) { throw 'Uninstall left application registration or installed files behind.' }
    if (-not (Test-Path -LiteralPath $database)) { throw 'Uninstall removed reminder data.' }
    @(
        'PASS: installer completed without elevation',
        'PASS: Windows Installed apps registration and version metadata',
        'PASS: Start menu shutdown shortcut arguments',
        'PASS: packaged app launched in safe shutdown preview mode',
        'PASS: packaged app initialized local storage',
        'PASS: real update helper waited for app exit, ran installer, and reopened the manager',
        'PASS: reminder contents and settings survived the local update handoff',
        'PASS: uninstall removed registration, shortcuts and executable',
        'PASS: reminder data survived uninstall',
        'Not tested: actual power-off, clean-machine install, SmartScreen reputation'
    ) | Tee-Object -FilePath (Join-Path $PSScriptRoot 'release\verification.txt')
} catch {
    Write-Warning "Verification failed. Inspect $testRoot. Installed test copy: $installed"
    if ($installed) {
        $failedExe = Join-Path $target 'Dayclose.exe'
        Get-Process Dayclose -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $failedExe } | Stop-Process -Force
        $cleanup = Join-Path $target 'unins000.exe'
        $expectedPrefix = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'build')) + [IO.Path]::DirectorySeparatorChar
        if ([IO.Path]::GetFullPath($target).StartsWith($expectedPrefix, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $cleanup)) {
            Start-Process -FilePath $cleanup -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART' -WindowStyle Hidden -Wait
        }
    }
    throw
}
