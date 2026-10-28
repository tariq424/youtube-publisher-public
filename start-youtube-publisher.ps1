param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
$cfg = Get-Content -LiteralPath (Join-Path $repo 'config.json') -Raw | ConvertFrom-Json
$port = [int]$cfg.port
$url = "http://127.0.0.1:$port"
New-Item -ItemType Directory -Force -Path $cfg.log_dir | Out-Null
$log = Join-Path $cfg.log_dir 'start.log'
function Write-Startup([string]$text) { Add-Content -LiteralPath $log -Value "$(Get-Date -Format o) $text"; Write-Host $text }
function Test-Publisher {
 try { return (Invoke-RestMethod "$url/health" -TimeoutSec 3).service -eq 'youtube-publisher' } catch { return $false }
}
if (-not (Test-Publisher)) {
 $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
 if ($listeners.Count) { Write-Startup "Port $port occupied by PID $($listeners[0].OwningProcess). Publisher not healthy."; exit 1 }
 $python = Join-Path $repo '.venv\Scripts\python.exe'
 if (-not (Test-Path -LiteralPath $python)) { Write-Startup 'Missing .venv. Complete README setup.'; exit 1 }
 Write-Startup "Starting independent publisher on $url"
 Start-Process -FilePath $python -ArgumentList ('"' + (Join-Path $repo 'app.py') + '"') -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $cfg.log_dir 'server.stdout.log') -RedirectStandardError (Join-Path $cfg.log_dir 'server.stderr.log')
 $deadline = (Get-Date).AddSeconds(40)
 while (-not (Test-Publisher) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 1 }
 if (-not (Test-Publisher)) { Write-Startup 'Publisher did not become healthy. See server.stderr.log.'; exit 1 }
}
Write-Startup "Publisher healthy at $url"
if (-not $NoBrowser) {
 $opera = @("$env:LOCALAPPDATA\Programs\Opera\opera.exe", "$env:ProgramFiles\Opera\opera.exe", "${env:ProgramFiles(x86)}\Opera\opera.exe") | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
 if ($opera) { Start-Process -FilePath $opera -ArgumentList $url -WindowStyle Hidden } else { Write-Startup "Opera not found. Open $url" }
}
exit 0
