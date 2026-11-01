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
$releaseVersion = python -c 'from version import APP_VERSION; print(APP_VERSION)'
if ($LASTEXITCODE -ne 0) { throw 'Could not read app version' }
& $Compiler '/Qp' "/DAppVersion=$releaseVersion" (Join-Path $PSScriptRoot 'installer.iss')
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
$installerName = "Dayclose-Setup-$releaseVersion.exe"
$installerPath = Join-Path $PSScriptRoot "release\$installerName"
$digest = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
"$digest  $installerName" | Set-Content -LiteralPath "$installerPath.sha256" -Encoding ascii
"$digest  $installerName" | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'release\SHA256.txt') -Encoding ascii
Write-Host "Installer: $installerPath"
