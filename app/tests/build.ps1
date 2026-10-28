# Configures and builds the test build (Debug, tests on) from a plain shell.
# Paths default to the owner's machine; override with GLUTTONY_QT / GLUTTONY_QT_TOOLS / GLUTTONY_VCVARS.
$ErrorActionPreference = 'Stop'
$qt     = if ($env:GLUTTONY_QT)       { $env:GLUTTONY_QT }       else { 'D:\allNewQT6\6.11.1\msvc2022_64' }
$tools  = if ($env:GLUTTONY_QT_TOOLS) { $env:GLUTTONY_QT_TOOLS } else { 'D:\allNewQT6\Tools' }
$vcvars = if ($env:GLUTTONY_VCVARS)   { $env:GLUTTONY_VCVARS }   else { 'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat' }
$src    = Split-Path $PSScriptRoot -Parent
$build  = Join-Path $src 'build\tests'

$env:PATH = "$tools\CMake_64\bin;$tools\Ninja;$qt\bin;$env:PATH"
cmd /c "`"$vcvars`" >nul && cmake -S `"$src`" -B `"$build`" -G Ninja -DCMAKE_BUILD_TYPE=Debug -DCMAKE_PREFIX_PATH=$qt -DGLUTTONY_BUILD_TESTS=ON && cmake --build `"$build`""
exit $LASTEXITCODE