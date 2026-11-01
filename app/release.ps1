# Builds the Release app and packages it for Windows: Gluttony.exe with its Qt (Qt Multimedia, for the timers'
# chime, included), the MSVC runtime, and no config\secrets.json (each install brings its own; README). Then checks
# the package: the files it must carry, and a run against the stub with nothing else on its PATH that grabs Home
# and loads the chime. Paths default to the owner's machine; override with GLUTTONY_QT / GLUTTONY_QT_TOOLS /
# GLUTTONY_VCVARS, as tests\build.ps1 does. -SkipCheck packages without the run.
param([switch]$SkipCheck)
$ErrorActionPreference = 'Stop'
$qt     = if ($env:GLUTTONY_QT)       { $env:GLUTTONY_QT }       else { 'D:\allNewQT6\6.11.1\msvc2022_64' }
$tools  = if ($env:GLUTTONY_QT_TOOLS) { $env:GLUTTONY_QT_TOOLS } else { 'D:\allNewQT6\Tools' }
$vcvars = if ($env:GLUTTONY_VCVARS)   { $env:GLUTTONY_VCVARS }   else { 'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat' }
$src    = $PSScriptRoot
$build  = Join-Path $src 'build\release'
$version = (Select-String -Path (Join-Path $src 'CMakeLists.txt') -Pattern 'project\(Gluttony VERSION ([0-9.]+)').Matches[0].Groups[1].Value
$name   = "Gluttony-$version-windows-x64"
$out    = Join-Path $src "build\$name"
$zip    = "$out.zip"

$env:PATH = "$tools\CMake_64\bin;$tools\Ninja;$qt\bin;$env:PATH"
cmd /c "`"$vcvars`" >nul && cmake -S `"$src`" -B `"$build`" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=$qt -DGLUTTONY_BUILD_TESTS=OFF && cmake --build `"$build`""
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (Test-Path $out) { Remove-Item -Recurse -Force $out }
if (Test-Path $zip) { Remove-Item -Force $zip }
New-Item -ItemType Directory $out | Out-Null
Copy-Item (Join-Path $build 'appGluttony.exe') (Join-Path $out 'Gluttony.exe')
# --qmldir lets windeployqt follow the pages' imports into Qt Quick, Controls and the rest.
& "$qt\bin\windeployqt.exe" --release --qmldir (Join-Path $src 'qml') --no-translations (Join-Path $out 'Gluttony.exe')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# The MSVC runtime beside the exe, so a friend's machine needs no redistributable installed.
$vc  = Split-Path (Split-Path (Split-Path $vcvars -Parent) -Parent) -Parent
$crt = Get-ChildItem "$vc\Redist\MSVC\*\x64\Microsoft.VC143.CRT" -Directory | Sort-Object FullName -Descending | Select-Object -First 1
if (-not $crt) { throw "no MSVC runtime under $vc\Redist\MSVC" }
Copy-Item "$($crt.FullName)\*.dll" $out

# The example says what a secrets.json holds; the real one never travels in the package.
New-Item -ItemType Directory (Join-Path $out 'config') | Out-Null
Copy-Item (Join-Path $src 'config\secrets.example.json') (Join-Path $out 'config')

# windeployqt 6.11 puts the plugin folders beside the exe (platforms\, imageformats\, multimedia\), not under plugins\;
# Qt finds them there.
$needed = @('Gluttony.exe', 'Qt6Core.dll', 'Qt6Quick.dll', 'Qt6Multimedia.dll', 'msvcp140.dll', 'vcruntime140.dll',
            'platforms\qwindows.dll', 'imageformats\qjpeg.dll', 'multimedia\ffmpegmediaplugin.dll',
            'qml\QtQuick\Controls')
$missing = @($needed | Where-Object { -not (Test-Path (Join-Path $out $_)) })
if (-not (Get-ChildItem $out -Filter 'avcodec-*.dll')) { $missing += 'avcodec-*.dll' }
if ($missing) { throw "the package is missing: $($missing -join ', ')" }
if (Test-Path (Join-Path $out 'config\secrets.json')) { throw 'the package must never carry a secrets.json' }

if (-not $SkipCheck) {
    $check = Join-Path $env:TEMP 'gluttony-release-check'
    if (Test-Path $check) { Remove-Item -Recurse -Force $check }
    New-Item -ItemType Directory $check | Out-Null
    $env:GLUTTONY_CHIME_CHECK = Join-Path $check 'chime.txt'
    try {
        & (Join-Path $src 'tests\stub\grab.ps1') -Out (Join-Path $check 'home.png') -Exe (Join-Path $out 'Gluttony.exe') -Fixture
    } finally {
        $env:GLUTTONY_CHIME_CHECK = ''
    }
    if (-not (Test-Path (Join-Path $check 'home.png'))) { throw 'the packaged app did not start (no grab)' }
    $chime = if (Test-Path (Join-Path $check 'chime.txt')) { (Get-Content (Join-Path $check 'chime.txt') -Raw).Trim() } else { 'nothing' }
    if ($chime -ne 'ready') { throw "the packaged app's chime did not load: $chime" }
    Write-Host "Checked: the package starts with no Qt on its PATH, and the chime loads ($check\home.png)."
}

Compress-Archive -Path "$out\*" -DestinationPath $zip
Write-Host "Packaged $zip"
