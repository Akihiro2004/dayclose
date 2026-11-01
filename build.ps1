$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python -m unittest -v test_reminders
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
$originalBuildPath = $env:PATH
try {
    # Prefer Windows' ICU/API libraries over unrelated DLLs injected by the host.
    $env:PATH = @(
        (Join-Path $env:SystemRoot 'System32'),
        $env:SystemRoot,
        (Split-Path (Get-Command python).Source)
    ) -join ';'
    python -m PyInstaller --noconfirm --clean --onefile --windowed --name Dayclose --icon assets/dayclose.ico --add-data "assets/dayclose.ico;assets" --version-file version-info.txt app.py
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
} finally {
    $env:PATH = $originalBuildPath
}
Write-Host "Built $PSScriptRoot\dist\Dayclose.exe"
