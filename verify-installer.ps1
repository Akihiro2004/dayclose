$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
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
$installer = Join-Path $PSScriptRoot 'release\Dayclose-Setup-1.0.0.exe'
$installed = $false
try {
    $arguments = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /TASKS="" /DIR="{0}" /GROUP="{1}" /LOG="{2}"' -f $target, $groupName, (Join-Path $testRoot 'install.log')
    $setup = Start-Process -FilePath $installer -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
    if ($setup.ExitCode -ne 0) { throw "Installer returned $($setup.ExitCode)." }
    $installed = $true
    $exe = Join-Path $target 'Dayclose.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw 'Installed executable missing.' }
    $entry = Get-ItemProperty $registry
    if ($entry.DisplayName -ne 'Dayclose' -or $entry.DisplayVersion -ne '1.0.0') { throw 'Installed apps metadata mismatch.' }
    $version = (Get-Item -LiteralPath $exe).VersionInfo
    if ($version.ProductName -ne 'Dayclose' -or $version.FileVersion -ne '1.0.0') { throw 'Executable metadata mismatch.' }
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
