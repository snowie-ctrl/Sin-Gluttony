# Copied from Pageturner Pageturner/tests/run.ps1 at ad9342e; GLUTTONY_ names, no WebP switch, the bundled heading font for offscreen runs.
# Runs the C++ tests (ctest) and then the QML helper tests (qmltestrunner),
# then prints one summary line per stage. Exits 0 only when both stages pass.
#   run.ps1                    everything
#   run.ps1 -R tst_reader      only C++ tests whose name matches
#   run.ps1 -NoQml             skip qmltestrunner
param([string]$R = '', [switch]$NoQml)
# Not 'Stop': ctest and qmltestrunner write to stderr, and when the caller
# redirects it (2>&1) PowerShell would turn the first such line into an error
# that ends the script before the QML stage runs.
$ErrorActionPreference = 'Continue'
$qt    = if ($env:GLUTTONY_QT)       { $env:GLUTTONY_QT }       else { 'D:\allNewQT6\6.11.1\msvc2022_64' }
$tools = if ($env:GLUTTONY_QT_TOOLS) { $env:GLUTTONY_QT_TOOLS } else { 'D:\allNewQT6\Tools' }
$src   = Split-Path $PSScriptRoot -Parent
$build = Join-Path $src 'build\tests'

$env:PATH = "$tools\CMake_64\bin;$qt\bin;$env:PATH"
# No window is needed to check logic; offscreen keeps runs quiet and works headless.
$env:QT_QPA_PLATFORM = 'offscreen'
# The offscreen platform looks for fonts in the Qt install, which ships none, and
# warns in every GUI test. The bundled Playfair Display gives it a directory to read.
$env:QT_QPA_FONTDIR = Join-Path $src 'assets\fonts\PlayfairDisplay'

# ---- C++ tests ----
# Both streams go through the pipeline as plain text, so nothing a native
# program prints can stop the script, and the output can be read afterwards.
$ctestArgs = @('--test-dir', $build, '--output-on-failure')
if ($R) { $ctestArgs += @('-R', $R) }
& ctest @ctestArgs 2>&1 | ForEach-Object { "$_" } | Tee-Object -Variable ctestLines
$ctestExit = $LASTEXITCODE

# The test executables print nothing here, so the failures are read from
# ctest's own list ("  2 - tst_api (Failed)").
$failedTests = @($ctestLines | ForEach-Object { if ($_ -match '^\s*\d+\s+-\s+(\S+)\s+\(') { $Matches[1] } })
if ($ctestExit -eq 0) {
    $ctestPassed = $true
    $ctestSummary = 'ctest: passed'
} else {
    $ctestPassed = $false
    $names = if ($failedTests.Count -gt 0) { $failedTests -join ', ' } else { "exit code $ctestExit" }
    $ctestSummary = "ctest: FAILED ($names)"
}
Write-Output $ctestSummary

# ---- QML tests ----
$qmlPassed = $true
$qmlDir = Join-Path $PSScriptRoot 'qml'
if ($NoQml) {
    $qmlSummary = 'qml: skipped (-NoQml)'
} elseif (-not (Get-ChildItem $qmlDir -Filter 'tst_*.qml' -ErrorAction SilentlyContinue)) {
    $qmlSummary = 'qml: no tests'
} else {
    # qmltestrunner prints nothing to this console, so it writes its results
    # to a file, which is shown here and counted.
    $results = Join-Path $build 'qml-results.txt'
    Remove-Item -LiteralPath $results -Force -ErrorAction SilentlyContinue
    & qmltestrunner -input $qmlDir -o "$results,txt" 2>&1 | ForEach-Object { "$_" }
    $qmlExit = $LASTEXITCODE
    if (Test-Path -LiteralPath $results) {
        $qmlLines = Get-Content -LiteralPath $results
        $qmlLines
        $passedCount = 0
        $failedCount = 0
        foreach ($line in $qmlLines) {
            if ($line -match '^Totals:\s+(\d+) passed,\s+(\d+) failed') {
                $passedCount += [int]$Matches[1]
                $failedCount += [int]$Matches[2]
            }
        }
        $qmlPassed = $qmlExit -eq 0 -and $failedCount -eq 0
        $qmlSummary = "qml: $passedCount passed, $failedCount failed"
        if ($qmlExit -ne 0 -and $failedCount -eq 0) { $qmlSummary += " (qmltestrunner exit code $qmlExit)" }
    } else {
        $qmlPassed = $false
        $qmlSummary = "qml: FAILED (no results file; qmltestrunner exit code $qmlExit)"
    }
    Write-Output $qmlSummary
}

Write-Output ''
Write-Output $ctestSummary
Write-Output $qmlSummary
if ($ctestPassed -and $qmlPassed) { exit 0 } else { exit 1 }
