$ErrorActionPreference = 'Stop'
$exe = Join-Path $PSScriptRoot 'dist\Dayclose.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'Build the application first using build.ps1.' }
$desktop = [Environment]::GetFolderPath('Desktop')
$startMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'Dayclose'
New-Item -ItemType Directory -Path $startMenu -Force | Out-Null
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in @($desktop, $startMenu)) {
    foreach ($entry in @(@('Reminders', ''), @('Review & Shut Down', '--shutdown'))) {
        $shortcut = $shell.CreateShortcut((Join-Path $folder ($entry[0] + '.lnk')))
        $shortcut.TargetPath = $exe
        $shortcut.Arguments = $entry[1]
        $shortcut.WorkingDirectory = $PSScriptRoot
        $shortcut.Description = 'Dayclose - local reminders'
        $shortcut.Save()
    }
}
Write-Host 'Created Reminders and Review & Shut Down shortcuts on Desktop and in Start.'
