param([string]$Compiler = '')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not $Compiler) {
    $candidates = @(
        'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        'C:\Program Files\Inno Setup 6\ISCC.exe'
    )
    $Compiler = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $Compiler -or -not (Test-Path -LiteralPath $Compiler)) {
    throw 'Install Inno Setup 6, or pass its ISCC.exe path using -Compiler.'
}
& (Join-Path $PSScriptRoot 'build.ps1')
& $Compiler '/Qp' (Join-Path $PSScriptRoot 'installer.iss')
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'release\Dayclose-Setup-1.0.0.exe') -Algorithm SHA256 |
    Format-List | Out-File -LiteralPath (Join-Path $PSScriptRoot 'release\SHA256.txt') -Encoding utf8
Write-Host "Installer: $PSScriptRoot\release\Dayclose-Setup-1.0.0.exe"
