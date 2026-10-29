# Copied from Pageturner Pageturner/tests/stub/grab.ps1 at ad9342e; Gluttony's switches and hooks, the stub run
# with the server's venv, no download seeding, -Kept and -Removed for the stub's kept lists and removed recipes.
# Runs the test build of the app against the stub API and saves a screenshot.
#   grab.ps1 -Out home.png
#   grab.ps1 -Out login.png -NewDevice                          (the sign-in form)
#   grab.ps1 -Out nothing.png -Diet "vegan;gluten,soy,egg"      (Home when nothing fits the diet)
#   grab.ps1 -Out quick.png -Query "kind=food&maxMinutes=30&difficulty=1&title=Quick fix"
#   grab.ps1 -Out recipe.png -Recipe 1
#   grab.ps1 -Out us.png -Recipe 1 -Click "<x>,<y>"             (click the US chip first)
#   grab.ps1 -Out gone.png -Recipe 999                          (a recipe that has gone)
#   grab.ps1 -Out down.png -HomeDown                            (Home when /home fails)
#   grab.ps1 -Out plates.png -PicturesFail                      (every picture a placeholder)
#   grab.ps1 -Out kept.png -Kept                                (Home with Cravings and Again?)
#   grab.ps1 -Out saved.png -Kept -Page saved-page              (the Saved page on Cravings)
#   grab.ps1 -Out actions.png -Kept -Recipe 1                   (the recipe page's actions, with a note)
#   grab.ps1 -Out removed.png -Kept -Removed 1 -Recipe 1        (a removed recipe its saver still opens)
#   grab.ps1 -Out settings.png -Page settings-page              (Settings)
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
    [string]$Removed = ''
)
$ErrorActionPreference = 'Stop'
$here   = $PSScriptRoot
$src    = Split-Path (Split-Path $here -Parent) -Parent
$repo   = Split-Path $src -Parent
$qt     = if ($env:GLUTTONY_QT) { $env:GLUTTONY_QT } else { 'D:\allNewQT6\6.11.1\msvc2022_64' }
$exe    = Join-Path $src 'build\tests\appGluttony.exe'
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

$stub = $null
try {
    $stub = Start-Process $python -ArgumentList "`"$here\stub_server.py`"" -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2

    $env:PATH                   = "$qt\bin;$env:PATH"
    $env:GLUTTONY_SECRETS       = $secrets
    $env:GLUTTONY_SETTINGS_DIR  = "$scratch\settings"
    $env:GLUTTONY_DATA_DIR      = "$scratch\data"
    # The basic render loop runs QML animations off the clock, so grabs are repeatable (as in Pageturner).
    $env:QSG_RENDER_LOOP        = 'basic'
    $env:GLUTTONY_START_PAGE    = $Page
    $env:GLUTTONY_START_RECIPE  = if ($Recipe) { "$Recipe" } else { '' }
    $env:GLUTTONY_START_QUERY   = $Query
    $env:GLUTTONY_TZ            = $Tz
    $env:GLUTTONY_GRAB          = $outFile
    $env:GLUTTONY_GRAB_DELAY    = "$Delay"
    $env:GLUTTONY_GRAB_SIZE     = $Size
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
