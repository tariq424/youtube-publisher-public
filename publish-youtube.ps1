param(
    [Parameter(Mandatory=$true)][string]$Job,
    [Parameter(Mandatory=$true)][string]$Channel,
    [ValidateSet('long','short')][string]$Kind = 'long',
    [switch]$Upload,
    [string]$Thumbnail = ''
)
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = 'python' }
$publisherArgs = @((Join-Path $PSScriptRoot 'youtube_publisher.py'), $Job, '--channel', $Channel, '--kind', $Kind)
if ($Upload) { $publisherArgs += '--upload' }
if ($Thumbnail) { $publisherArgs += @('--thumbnail', $Thumbnail) }
& $python @publisherArgs
exit $LASTEXITCODE
