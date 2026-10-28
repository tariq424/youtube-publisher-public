# Standalone multi-channel YouTube publisher

All code lives in F:\youtube-uploads. Job folders are read-only inputs. No pipeline
code dependency, Claude, or Telegram. Codex CLI must be installed and authenticated.
The publisher checks PATH, then the desktop app's bundled Codex executable under
LOCALAPPDATA. Python CLI `--codex` can specify an explicit executable.

## Setup

```powershell
cd F:\youtube-uploads
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Playwright uses installed Chrome and one shared profile for all channels.
Global `config.json` sets `chrome_profile` to `F:\youtube-uploads\profiles\main`,
`playwright_headless` to false, and `upload_timeout_seconds` to 600. The Python
`--timeout` option overrides that upload timeout when supplied.

One-time setup:

1. Launch Chrome with `--user-data-dir="F:\youtube-uploads\profiles\main"`.
2. Log into the main Google account.
3. Navigate to https://studio.youtube.com and confirm all channels appear in the account switcher.
4. Close Chrome before uploading.

The profile root must contain `Local State`. Missing profile stops uploads before
metadata generation or browser launch. Use English Studio. Regular Chrome's main
User Data directory is unsupported by modern automation. No uploader was run for
this shared-profile update.

## Commands

After the shared profile is signed in, run the setup test without repeating login:

```powershell
.\setup-and-test.ps1 -SkipSetup -Job 20261013_100822 -Channel Moonspots
```

Generate metadata only:

```powershell
.\publish-youtube.ps1 -Job 20261013_100822 -Channel Moonspots
```

Upload Private after review:

```powershell
.\publish-youtube.ps1 -Job 20261013_100822 -Channel Moonspots -Upload
```

Optional -Kind short selects the Short; default is long. -Thumbnail overrides the
existing thumbnail_9_16.png. Python CLI also accepts --video and --timeout.

## Channel configuration

channel_configs\moonspots.json and youtour.json define `youtube_channel_name`
(Moonspots / YouTour) and metadata defaults, with no per-channel profile field.
Before Create/Upload, the uploader opens the account menu, clicks Switch account,
selects exactly one matching display name, and verifies that name in Studio's
channel sidebar. Missing, ambiguous, or unverifiable channels stop the upload.
One shared-profile lock prevents concurrent uploads across different channels.
Add another JSON file for future channels. Names are case-insensitive.

title_prefix is prepended. Empty description_template preserves the generated hook;
otherwise it replaces the hook and expands {hook} if present. Result must have 2–3
nonempty lines. Original description, credits and chapter timestamps are always
appended verbatim. default_tags precede generated tags, deduplicated to exactly 15.
default_category is applied. Private and made_for_kids=false are mandatory.
Changed config invalidates cached metadata; review/remove metadata to regenerate.
Missing channel configs stop every run. Missing signed-in profile roots stop uploads
before metadata generation or launching Chrome; the program never creates logins.

## Output and recovery

All generated files live under uploads\<channel>\<job_id>:
youtube_long_metadata.json, youtube_long_upload.json and youtube_url.txt.
Shorts use youtube_short_metadata.json, youtube_short_upload.json and youtube_short_url.txt.
logs\workflow.log tracks starts, completions and failures. Profiles, uploads, logs,
virtual environments and caches are gitignored.

URLs are saved after Save and persisted Private visibility verification. State can
hold a provisional URL earlier for recovery. Existing state blocks retries to avoid
duplicate uploads; inspect Studio before manually clearing it. Locks prevent concurrent
runs; inspect state before removing stale locks after a killed process.

Credits and line endings are preserved after UTF-8 BOM removal. Existing chapters
must start at zero with at least 3 entries spaced >=10 seconds. Narration is never
modified. Codex receives description and plan narration for metadata, not the video
or profile credentials. Length limits are enforced without truncating credits.
YouTube custom-thumbnail restrictions, login prompts, or Studio UI changes may need
manual intervention. No CAPTCHA bypass or public/unlisted publishing.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Five original offline tests retained and adapted, plus channel config tests.
Historical smoke-test outcome: SMOKE_TEST.md; local workflow log: logs\workflow.log.

References:
- https://developers.openai.com/codex/noninteractive
- https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context
- https://support.google.com/youtube/answer/57407
- https://support.google.com/youtube/answer/9884579
- https://support.google.com/youtube/answer/3046356
