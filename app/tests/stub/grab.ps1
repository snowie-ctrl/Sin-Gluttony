# Copied from Pageturner Pageturner/tests/stub/grab.ps1 at ad9342e; Gluttony's switches and hooks, the stub run
# with the server's venv, no download seeding, -Kept and -Removed for the stub's kept lists and removed recipes,
# -Fixture to serve the fixture's recipes whether or not a snapshot is present, -Cook and -Offline for cook mode and an
# offline start.
# Runs the test build of the app against the stub API and saves a screenshot. The stub serves snapshot/ when it
# exists; the examples that name an id pass -Fixture, so they open the fixture's four recipes (ids 1-4), which have
# no pictures, so those grabs show placeholders. Without -Fixture, pass an id from the snapshot instead.
#   grab.ps1 -Out home.png
#   grab.ps1 -Out login.png -NewDevice                          (the sign-in form)
#   grab.ps1 -Out nothing.png -Diet "vegan;gluten,soy,egg"      (Home when nothing fits the diet)
#   grab.ps1 -Out quick.png -Query "kind=food&maxMinutes=30&difficulty=1&title=Quick fix"
#   grab.ps1 -Out recipe.png -Fixture -Recipe 1
#   grab.ps1 -Out us.png -Fixture -Recipe 1 -Click "<x>,<y>"    (click the US chip first)
#   grab.ps1 -Out gone.png -Recipe 999                          (a recipe that has gone)
#   grab.ps1 -Out down.png -HomeDown                            (Home when /home fails)
#   grab.ps1 -Out plates.png -PicturesFail                      (every picture a placeholder)
#   grab.ps1 -Out kept.png -Kept                                (Home with Cravings and Again?)
#   grab.ps1 -Out saved.png -Kept -Page saved-page              (the Saved page on Cravings)
#   grab.ps1 -Out actions.png -Fixture -Kept -Recipe 1          (the recipe page's actions, with a note)
#   grab.ps1 -Out removed.png -Fixture -Kept -Removed 1 -Recipe 1 (a removed recipe its saver still opens)
#   grab.ps1 -Out settings.png -Page settings-page              (Settings)
#   grab.ps1 -Out cook.png -Fixture -Recipe 1 -Cook               (cook mode on a recipe)
#   grab.ps1 -Out offline.png -Kept -Offline                      (an offline start: Home's saved rows)
#   grab.ps1 -Out offsaved.png -Kept -Offline -Page saved-page    (an offline start: the kept lists)
#   .\grab.ps1 -Out home.png -Exe ..\..\build\Gluttony-1.0-windows-x64\Gluttony.exe -Fixture   (a packaged build)
param(
    [Parameter(Mandatory = $true)][string]$Out,
    [string]$Page = 'home-page',
    [int]$Recipe = 0,
    [string]$Query = '',
    [int]$Delay = 8000,
    [string]$Click = '',
    [int]$ClickDelay = 5000,
    [string]$Size = '',
    [string]$Tz = 'America/Chicago',
    [switch]$Lan,
    [switch]$NewDevice,
    [string]$Diet = '',
    [switch]$HomeDown,
    [switch]$PicturesFail,
    [int]$Slow = 0,
    [switch]$Kept,
    [string]$Removed = '',
    [switch]$Fixture,
    [switch]$Cook,
    [switch]$Offline,
    [string]$Exe = ''
)
$ErrorActionPreference = 'Stop'
$here   = $PSScriptRoot
$src    = Split-Path (Split-Path $here -Parent) -Parent
$repo   = Split-Path $src -Parent
$qt     = if ($env:GLUTTONY_QT) { $env:GLUTTONY_QT } else { 'D:\allNewQT6\6.11.1\msvc2022_64' }
# -Exe runs another build (release.ps1's package) instead of the test build.
$exe    = if ($Exe) { (Resolve-Path -LiteralPath $Exe).Path } else { Join-Path $src 'build\tests\appGluttony.exe' }
# A git worktree has no venv of its own, so GLUTTONY_PYTHON can point at the main checkout's.
$python = if ($env:GLUTTONY_PYTHON) { $env:GLUTTONY_PYTHON } else { Join-Path $repo 'server\.venv\Scripts\python.exe' }

# A bare filename has no parent folder, so it lands in the current one.
$outDir = Split-Path $Out -Parent
if (-not $outDir) { $outDir = '.' }
$outFile = (Resolve-Path -LiteralPath $outDir).Path + '\' + (Split-Path $Out -Leaf)
if (Test-Path -LiteralPath $outFile) { Remove-Item -LiteralPath $outFile -Force }

$secrets = Join-Path $env:TEMP 'gluttony-stub-secrets.json'
# With -Lan the stub is also the home address; it answers /ping, so the app picks it.
$base = 'http://127.0.0.1:5079/api/gluttony'
$json = if ($Lan) { "{`"apiBase`": `"$base`", `"lanApiBase`": `"$base`"}" } else { "{`"apiBase`": `"$base`"}" }
$json | Set-Content -Encoding ascii $secrets

# A fresh settings folder and data folder each run, so runs don't affect each other or the owner's.
$scratch = Join-Path $env:TEMP ('gluttony-grab-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force "$scratch\settings", "$scratch\data" | Out-Null

$env:STUB_NEW_DEVICE    = if ($NewDevice) { '1' } else { '' }
$env:STUB_DIET          = $Diet
$env:STUB_HOME_DOWN     = if ($HomeDown) { '1' } else { '' }
$env:STUB_PICTURES_FAIL = if ($PicturesFail) { '1' } else { '' }
$env:STUB_SLOW          = if ($Slow) { "$Slow" } else { '' }
$env:STUB_KEPT          = if ($Kept) { '1' } else { '' }
$env:STUB_REMOVED       = $Removed
# Always set, so a STUB_SNAPSHOT left in the caller's shell never changes what a grab serves.
$env:STUB_SNAPSHOT      = if ($Fixture) { Join-Path $here 'fixture' } else { '' }
$env:GLUTTONY_START_COOK = if ($Cook) { '1' } else { '' }

$stub = $null
try {
    $stub = Start-Process $python -ArgumentList "`"$here\stub_server.py`"" -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2

    # A package must carry its own Qt: nothing else is put on its PATH, so a missing DLL shows here, not on a
    # friend's machine.
    $env:PATH                   = if ($Exe) { "$env:SystemRoot\System32;$env:SystemRoot" } else { "$qt\bin;$env:PATH" }
    if ($Exe) {
        # Qt also finds its DLLs and plugins through these, so a shell with Qt set up must not leak them into the
        # package's run.
        foreach ($name in 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'QML_IMPORT_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH') {
            Set-Item -Path "Env:$name" -Value ''
        }
    }
    $env:GLUTTONY_SECRETS       = $secrets
    $env:GLUTTONY_SETTINGS_DIR  = "$scratch\settings"
    $env:GLUTTONY_DATA_DIR      = "$scratch\data"
    # The basic render loop runs QML animations off the clock, so grabs are repeatable (as in Pageturner).
    $env:QSG_RENDER_LOOP        = 'basic'
    $env:GLUTTONY_TZ            = $Tz
    $env:GLUTTONY_GRAB_SIZE     = $Size

    if ($Offline) {
        # A first run signs in and keeps the saved recipes on the device (the manifest's refresh), then the stub
        # stops, so the grab is an offline start of the account signed in last.
        $env:GLUTTONY_START_PAGE   = 'home-page'
        $env:GLUTTONY_START_RECIPE = ''
        $env:GLUTTONY_START_QUERY  = ''
        $env:GLUTTONY_CLICK        = ''
        $env:GLUTTONY_GRAB         = Join-Path $scratch 'first-run.png'
        $env:GLUTTONY_GRAB_DELAY   = '6000'
        Start-Process $exe -Wait
        Stop-Process -Id $stub.Id -ErrorAction SilentlyContinue
        $stub = $null
    }

    $env:GLUTTONY_START_PAGE    = $Page
    $env:GLUTTONY_START_RECIPE  = if ($Recipe) { "$Recipe" } else { '' }
    $env:GLUTTONY_START_QUERY   = $Query
    $env:GLUTTONY_GRAB          = $outFile
    $env:GLUTTONY_GRAB_DELAY    = "$Delay"
    $env:GLUTTONY_CLICK         = $Click
    $env:GLUTTONY_CLICK_DELAY   = "$ClickDelay"
    Start-Process $exe -Wait
} finally {
    if ($stub) { Stop-Process -Id $stub.Id -ErrorAction SilentlyContinue }
    Remove-Item -Recurse -Force $scratch -ErrorAction SilentlyContinue
}
if (-not (Test-Path -LiteralPath $outFile)) {
    throw "The app exited without saving $outFile (did it start? is the build in $exe current?)"
}
Write-Output "Saved $outFile"
