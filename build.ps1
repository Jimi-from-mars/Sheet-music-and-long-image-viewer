param([switch]$Test, [switch]$Offline, [string]$OutputName = '图片分屏查看器_v2.0.exe')
$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
Push-Location -LiteralPath $projectDir
$oldCargoHome = $env:CARGO_HOME
$oldPath = $env:PATH
try {
    foreach ($tool in @('rustc','cargo','clang.exe','lld-link.exe','windres.exe')) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Missing build tool: $tool" }
    }
    $projectCache = Join-Path $projectDir '.build\cargo'
    $hasProjectCache = Test-Path (Join-Path $projectCache 'registry')
    if ($hasProjectCache) { $env:CARGO_HOME = $projectCache }
    $env:PATH = (Join-Path $projectDir '.cargo') + ';' + $oldPath
    & rustc --edition=2024 --target x86_64-pc-windows-gnu -C linker=.cargo/linker.cmd -C target-feature=+crt-static .cargo\dlltool.rs -o .cargo\split-image-dlltool.exe
    if ($LASTEXITCODE -ne 0) { throw 'Failed to prepare Unicode import-library adapter' }
    $cargoArgs = @('--locked')
    if ($Offline -or $hasProjectCache) { $cargoArgs += '--offline' }
    if ($Test) {
        & cargo test @cargoArgs
        if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    }
    & cargo build --release @cargoArgs
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    $compiledExe = Join-Path $projectDir 'target\x86_64-pc-windows-gnu\release\split-image-viewer.exe'
    if ([IO.Path]::GetFileName($OutputName) -ne $OutputName) { throw 'OutputName must be a filename' }
    $outputExe = Join-Path $projectDir $OutputName
    Copy-Item -LiteralPath $compiledExe -Destination $outputExe -Force
    Write-Host "Created: $outputExe"
} finally {
    $env:CARGO_HOME = $oldCargoHome
    $env:PATH = $oldPath
    Pop-Location
}
