$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python -m unittest discover -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
python release_meta.py
if ($LASTEXITCODE -ne 0) { throw 'Version metadata generation failed' }
$helperCompiler = Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'build') -Force | Out-Null
& $helperCompiler '/nologo' '/target:winexe' '/reference:System.Windows.Forms.dll' '/out:build\Dayclose.UpdateHelper.exe' 'UpdateHelper.cs'
if ($LASTEXITCODE -ne 0) { throw 'Update helper compilation failed' }
$originalBuildPath = $env:PATH
try {
    # Prefer Windows' ICU/API libraries over unrelated DLLs injected by the host.
    $env:PATH = @(
        (Join-Path $env:SystemRoot 'System32'),
        $env:SystemRoot,
        (Split-Path (Get-Command python).Source)
    ) -join ';'
    python -m PyInstaller --noconfirm --clean --onefile --windowed --name Dayclose --icon assets/dayclose.ico --add-data "assets/dayclose.ico;assets" --add-data "build/Dayclose.UpdateHelper.exe;." --version-file version-info.txt app.py
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
} finally {
    $env:PATH = $originalBuildPath
}
Write-Host "Built $PSScriptRoot\dist\Dayclose.exe"
