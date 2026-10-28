# setup-and-test.ps1
# Sets up the Chrome profile, verifies login, and runs the metadata test.
# Run from F:\youtube-uploads\
#
# Usage:
#   .\setup-and-test.ps1                          # Setup profile + metadata test
#   .\setup-and-test.ps1 -SkipSetup               # Metadata test only
#   .\setup-and-test.ps1 -Job 20261013_100822 -Channel Moonspots
#   .\setup-and-test.ps1 -Upload                  # Actually upload after review

param(
    [string]$Job = "20261013_100822",
    [string]$Channel = "Moonspots",
    [switch]$SkipSetup,
    [switch]$Upload
)

$ErrorActionPreference = "Stop"

# --- Configuration ---
$RepoPath = $PSScriptRoot
$Config = Get-Content -LiteralPath (Join-Path $RepoPath 'config.json') -Raw | ConvertFrom-Json
$ProfilePath = $Config.chrome_profile
if (-not [IO.Path]::IsPathRooted($ProfilePath)) { $ProfilePath = Join-Path $RepoPath $ProfilePath }
$JobPath = "F:\videos\video_studio\jobs\$Job\output"
$ChromePaths = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)

Write-Host ""
Write-Host "=== YouTube Publisher Setup & Test ===" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: Find Chrome ---
if (-not $SkipSetup) {
    Write-Host "[1/6] Locating Chrome..." -ForegroundColor Yellow
    $ChromeExe = $null
    foreach ($path in $ChromePaths) {
        if (Test-Path $path) {
            $ChromeExe = $path
            break
        }
    }
    if (-not $ChromeExe) {
        Write-Host "ERROR: Chrome not found. Install Google Chrome or set the path manually." -ForegroundColor Red
        exit 1
    }
    Write-Host "      Found: $ChromeExe" -ForegroundColor Green

    # --- Step 2: Create profile folder ---
    Write-Host "[2/6] Creating profile folder..." -ForegroundColor Yellow
    if (-not (Test-Path $ProfilePath)) {
        New-Item -ItemType Directory -Path $ProfilePath -Force | Out-Null
        Write-Host "      Created: $ProfilePath" -ForegroundColor Green
    } else {
        Write-Host "      Already exists: $ProfilePath" -ForegroundColor Green
    }

    # --- Step 3: Launch Chrome for login ---
    Write-Host "[3/6] Launching Chrome with the shared profile..." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "      ACTION REQUIRED:" -ForegroundColor Magenta
    Write-Host "      1. Log into your main Google account in the Chrome window that opens."
    Write-Host "      2. Navigate to: https://studio.youtube.com"
    Write-Host "      3. Verify your channels (Moonspots, YouTour) appear in the switcher."
    Write-Host "      4. Close the Chrome window when done."
    Write-Host ""
    Write-Host "      Press ENTER when you're ready to open Chrome..."
    Read-Host | Out-Null

    Start-Process -FilePath $ChromeExe -ArgumentList "--user-data-dir=`"$ProfilePath`"", "https://studio.youtube.com" -WindowStyle Hidden

    Write-Host ""
    Write-Host "      Press ENTER after you've logged in and closed Chrome..."
    Read-Host | Out-Null

    # --- Step 4: Verify profile exists ---
    Write-Host "[4/6] Verifying profile..." -ForegroundColor Yellow
    if (-not (Test-Path -LiteralPath (Join-Path $ProfilePath 'Local State'))) {
        Write-Host "WARNING: Profile\Default folder not found. You may not have completed login." -ForegroundColor Yellow
        Write-Host "         Continue anyway? (y/n)"
        if ((Read-Host) -ne "y") { exit 1 }
    } else {
        Write-Host "      Profile verified." -ForegroundColor Green
    }
} else {
    Write-Host "[1-4/6] Skipped setup steps (--SkipSetup)." -ForegroundColor DarkGray
}

# --- Step 5: Verify job folder and files ---
Write-Host "[5/6] Verifying job folder for $Job..." -ForegroundColor Yellow
if (-not (Test-Path $JobPath)) {
    Write-Host "ERROR: Job folder not found: $JobPath" -ForegroundColor Red
    Write-Host "       Check the job ID and try again." -ForegroundColor Red
    exit 1
}

$Videos = @(Get-ChildItem -LiteralPath $JobPath -Filter "*_explainer_*.mp4")
if ($Videos.Count -ne 1) { throw 'Expected exactly one explainer MP4 in the job output.' }
$Mp4 = $Videos[0]
$Thumb = Get-Item -LiteralPath (Join-Path $JobPath 'thumbnail_9_16.png') -ErrorAction SilentlyContinue
$Desc = Get-Item -LiteralPath (Join-Path $JobPath 'youtube_description.txt') -ErrorAction SilentlyContinue

if (-not $Mp4) {
    Write-Host "ERROR: No MP4 found in $JobPath" -ForegroundColor Red
    exit 1
}
if (-not $Thumb) {
    throw 'Required thumbnail_9_16.png not found.'
}
if (-not $Desc) {
    throw 'Required youtube_description.txt not found.'
}

Write-Host "      MP4:         $($Mp4.Name)" -ForegroundColor Green
if ($Thumb) { Write-Host "      Thumbnail:   $($Thumb.Name)" -ForegroundColor Green }
if ($Desc) { Write-Host "      Description: $($Desc.Name)" -ForegroundColor Green }

# --- Step 6: Run the publisher ---
Write-Host "[6/6] Running the publisher..." -ForegroundColor Yellow
Write-Host ""

Set-Location $RepoPath

if ($Upload) {
    Write-Host "      MODE: UPLOAD (will push to YouTube as Private)" -ForegroundColor Magenta
    Write-Host "      Press ENTER to confirm and start the upload..."
    Read-Host | Out-Null
    & ".\publish-youtube.ps1" -Job $Job -Channel $Channel -Upload
} else {
    Write-Host "      MODE: METADATA ONLY (no upload)" -ForegroundColor Cyan
    & ".\publish-youtube.ps1" -Job $Job -Channel $Channel
}

Write-Host ""

if ($LASTEXITCODE -ne 0) {
    Write-Host 'Publisher failed. See logs\workflow.log; setup is not complete.' -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "=== Done ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Metadata: $RepoPath\uploads\$($Channel.ToLowerInvariant())\$Job\youtube_long_metadata.json" -ForegroundColor White
Write-Host "To review, then upload:"
Write-Host "  .\setup-and-test.ps1 -Job $Job -Channel $Channel -Upload" -ForegroundColor Gray
Write-Host ""
