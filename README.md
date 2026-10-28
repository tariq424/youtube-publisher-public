# YouTube Publisher

Independent local app at **http://127.0.0.1:42030**. Finished-job inputs are read-only.
The unchanged `F:\youtube-uploads` remains a fallback. The GitHub repo was renamed
to `tariq424/youtube-publisher`; only this copy's origin was updated.

## Setup

```powershell
cd F:\youtube-publisher
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\start-youtube-publisher.ps1
.\install-startup-task.ps1
```

Installed Google Chrome is used for persistent profiles. Chromium is also installed
for browser tests. `config.json` defines the port, dedicated profile, logs, input jobs,
headed/headless mode and upload timeout. No pipeline modules, config, ports or
processes are used. There is no Ollama/Phi-4 runtime dependency; metadata regeneration
uses the existing Codex backend. The requested publisher_logic.py was absent in the
source, so it is implemented here for discovery, defaults and validation.

The source profile was deep-copied. Close Chrome using the publisher's profile before
publishing. If the copied login is unavailable, open Chrome once with
`--user-data-dir="F:\youtube-publisher\profiles\main"`, sign into the main account,
check Moonspots/YouTour in Studio's switcher, then close Chrome. All uploads use the
same dedicated profile and verify the chosen channel before transferring a file.
The Moonspots config key maps to the actual Studio display name **MoonSpot**;
this was verified during the live test. YouTour's display name is unchanged.

## Workflow

Choose channel/job and Short or Explainer, preview the MP4, review metadata, choose a
thumbnail (existing, custom, or extracted frame), then Publish. Private and No are
defaults; the GUI also supports Unlisted/Public and Yes when explicitly selected.
First live upload is headed. Screenshots before/after actions and timestamped logs
appear in Publishing activity. Source credits are protected; chapters can be edited
or omitted and are validated against the real video duration.

`?job=<id>` preselects a job. Related Video/End Screen dropdowns read published records
across channels, deduplicate IDs and omit records marked deleted. Target eligibility
is checked by YouTube: Related Video may be restricted to your current channel and
feature access; cross-channel targets can require manual linking. End screens require
eligible videos of at least 25 seconds. Linking failure preserves upload success and
shows a direct Studio URL and exact failure; it never uploads the video again.

Drafts, generated thumbnails, progress state, screenshots, URLs and published records
are saved in `uploads/<channel>/<job>/`. Both video types can have records:
`published.json` plus `published_<type>.json` when needed. Nothing is written back to
the finished-job folder; error screenshots are stored in the publisher's job folder.
Logs: `logs/start.log`, `logs/publisher.log`, server stdout/stderr.

Retry recovers the remembered video ID (or finds exactly one existing title in Studio)
and resumes metadata/linking. Restart requires explicit duplicate-risk confirmation.
Cancel preserves existing Studio drafts. After a crash, a stale profile lock may need
manual removal only after confirming the publisher's Chrome process has ended.
Progress tasks survive server restarts; an interrupted task is reported recoverable.

## Tests and startup

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The logon task uses absolute paths and fires 60 seconds after Windows sign-in.
`start-youtube-publisher.ps1 -NoBrowser` starts without opening Opera.
Conflicts on 42030 fail clearly rather than moving to a different port.
No YouTube Data API, Telegram, video generation, or shared pipeline runtime.
