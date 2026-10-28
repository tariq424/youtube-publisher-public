# YouTube Publisher — project context

Last updated: October 15, 2026.

## Purpose and boundaries

Standalone Windows application for reviewing finished Video Studio jobs and
uploading them through YouTube Studio with Playwright. Active working repository:
`F:\youtube-publisher`, GitHub `https://github.com/tariq424/youtube-publisher`,
branch `main`. Local GUI: `http://127.0.0.1:42030`.

The former `F:\youtube-uploads` is an unchanged fallback. Do not modify it or the
pipeline repository `F:\code\video-studio`. Finished jobs under
`F:\videos\video_studio\jobs\<job_id>\output` are read-only inputs. Do not rewrite
narration or scripts. Preserve description credits and chapter timestamps.

This publisher does not generate videos, call pipeline APIs, use Telegram/Claude,
or depend on Ollama or Pinokio. YouTube interactions use browser automation, not
the YouTube Data API. Never re-upload a video just because processing or linking
verification failed; recover its recorded YouTube video ID.

## Architecture

| Component | Responsibility |
| --- | --- |
| `app.py` | Local Flask server; job discovery, media streaming, metadata, thumbnails, drafts, publish workers, progress screenshots and cancellation routes. |
| `publisher_logic.py` | Read-only job/asset discovery, duration probing, channel defaults, credits/chapters handling, form validation, thumbnail paths and published-record discovery. |
| `youtube_publisher.py` | Existing CLI metadata/publishing backend and GUI integration. Metadata regeneration uses the authenticated local Codex CLI. |
| `studio_automation.py` | Headed persistent Chrome workflow: select and verify channel, upload, fill fields, save, wait for processing, resume existing IDs, optional linking and verification. |
| `templates/`, `static/` | GUI for Short/Explainer review, MP4 preview, metadata editing, thumbnail selection/extraction, drafts and publishing activity. |
| `config.json` | Port, shared Chrome profile, input jobs root, logs, headed/headless setting and upload timeout. |
| `channel_configs/` | Per-channel Studio display name and metadata defaults. |
| `start-youtube-publisher.ps1` | Starts/checks this app, detects its port conflict, uses absolute paths and optionally opens Opera. |
| `install-startup-task.ps1` | Registers `Start YouTube Publisher`, 60 seconds after interactive Windows logon. |
| `publish-youtube.ps1`, `setup-and-test.ps1` | CLI entry points; see `README-youtube.md` for their workflow. |
| `branding/moonspot/` | Custom video thumbnail, banner, avatar, watermark, channel copy and image-generation prompts. |

The runtime is the repository's `.venv`. Dependencies are Flask, Playwright,
Pillow and imageio-ffmpeg. Installed Google Chrome uses the dedicated persistent
profile `F:\youtube-publisher\profiles\main`. All channels share this login;
automation selects the requested channel through Studio's account switcher and
verifies its exact name. The config key `moonspots` maps to **MoonSpot**. YouTour
has its own config but shares the same profile. Do not launch simultaneous browser
automation processes against this profile. The in-app browser and this Chrome
profile are separate browser sessions; login/channel state must be checked in the
session actually performing the upload.

## Data flow and persistence

1. Discover a completed job and select its Short or Explainer asset, excluding
   temporary/test/edit backup videos.
2. Load original description, credits and chapters; apply channel defaults.
   Generate metadata through Codex when requested. Validate before uploading.
3. Review/save a draft and choose a thumbnail. Private and not-made-for-kids are
   defaults; the GUI permits explicit alternative selections.
4. Start a background publish task. Save step events/screenshots and automation
   state as work proceeds. Remember the YouTube ID as soon as it is available.
5. Save the upload and wait up to the configured processing timeout for persisted
   visibility. Resume uses the same ID, including finalized videos still Pending.
6. Optionally set Shorts Related Video or a long-form End Screen. Linking failure
   preserves upload success and provides a direct Studio URL for recovery.
7. Save the resulting URL/record locally, without writing to the source job folder.

Runtime files live under `uploads/<channel>/<job>/`: `draft.json`, metadata,
`automation_<kind>.json`, published records/URL and per-task screenshot folders.
The picker reads local published records across channels, including explicitly
imported source records marked as imports rather than app uploads. Logs are under
`logs/`, including `publisher.log`, `start.log` and `workflow.log`. Profiles,
uploads, logs, work helpers and `.venv` are ignored by Git. Original generated PNGs
and Studio evidence screenshots in the branding directory are also ignored; final
branding exports and prompts are tracked.

## Verified live results

- Job `20261011_082753`, channel **MoonSpot** (channel ID
  `UC9pogqA60l8UKSnniBfnPbQ`): AI's "1942 moment", the superintelligence race and
  Claude consciousness debate, based on a Moonshots/Peter Diamandis episode.
- Exactly one video uploaded for this trial: `iAkaTlE2__g`,
  `https://www.youtube.com/watch?v=iAkaTlE2__g`. Verified Private,
  not-made-for-kids, correct title and actual playback. Fifteen video tags and
  twelve chapters; source credits preserved.
- Long-form end screen saved and verified after reload: original public source
  episode `LRdb8UmPnh0`, top-right, `13:33:02` through `13:48:02` (Studio's
  minutes:seconds:frames clock). YouTube hides end screens while a video is Private.
  A Private target was unsuitable because YouTube warns it can substitute it.
- Earlier successful job `20261013_023528`: `aVqMNDA9Yyg`, "God's Eye View Just
  Got a Massive Upgrade", also Private with playback verified.
- Earlier interrupted job `20261013_100822`: `TfWacUL-m3s` remained Pending at its
  last inspection. It was not deleted or recorded as a successful publish. Inspect
  that ID before retrying the job; do not create an accidental duplicate.
- MoonSpot banner, crescent avatar, watermark and description were published;
  Studio confirmed Changes published and persistence was checked after reload.
  Fifteen channel keywords were saved and verified by reopening Channel settings.
  Channel name and handle were retained; no contact details were invented.

## Current blocker: custom thumbnail feature access

The generated thumbnail is `branding/moonspot/thumbnail.jpg`, with headline
"AI'S 1942 MOMENT". It has **not** been applied to `iAkaTlE2__g`.

Earlier reports that an extracted custom thumbnail had saved were incorrect:
setting the file input did not establish YouTube acceptance. The adapter now
requires a visible Uploaded thumbnail preview and fails clearly while preserving
the existing upload if acceptance is not confirmed.

In the automation profile, clicking Upload file opens "Unlock more on YouTube"
and asks for phone verification. MoonSpot's Feature eligibility showed Standard
features Enabled, Intermediate features Eligible, and Advanced features Eligible.
Meanwhile, the user supplied a verification page saying the phone was already
verified and subsequently showed the MoonSpot crescent avatar in their browser.
The user is on the correct channel in that screenshot; do not repeatedly assume
they selected the wrong channel or insist they repeat verification without new
evidence. The shared Google login is the user's account, and MoonSpot is a channel
under that account. Subscription status does not resolve the observed mismatch.

Next task: investigate the conflicting feature status/session state, starting from
MoonSpot's actual Studio feature eligibility and verification flow. Once thumbnail
access works, update the **existing** video, wait for save completion, reload and
verify its uploaded thumbnail. Keep visibility Private and preserve metadata,
credits, chapters and end screen. Do not claim success based solely on file selection.

## Tests, startup and remaining scope

Last offline run: **19 tests passed**. Command:

```powershell
cd F:\youtube-publisher
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Coverage includes inherited backend behavior, media range streaming, validation,
credits preservation, draft isolation, thumbnail resizing, linking-failure recovery
and frame-preserving last-15-seconds timecodes. Live long-form upload and end screen
were verified. Shorts Related Video remains unproved live.

Launch with `start-youtube-publisher.ps1`; `-NoBrowser` suppresses Opera. The logon
task is installed and uses absolute paths. Actual reboot recovery testing was
explicitly deferred by the user. This is not evidence that the separate Video Studio,
WanGP, Ollama or Pinokio startup chain has been reboot-tested or completed here.

Only selected trial jobs were uploaded; there is no authorization to assume every
job folder should now be bulk-published. The current work is the existing MoonSpot
video and its branding. See `TEST_REPORT.md` and the local runtime evidence for details.

## YouSocial job completed October 15, 2026

User requested both versions of `20261014_194800`, plus a new banner, thumbnail
and insignia. Verified YouSocial `@ASocialSquare`, channel ID
`UCCXCpr98-N1JJ24Yat6nCrg`, in the shared login. All feature tiers were Enabled.

- Long: `UEpu0f1cBN4`, "Tristan Harris's AI Warning: Who Is Really in Control?",
  15:42; custom generated thumbnail accepted and verified after reload.
- Short: `HFSr6AnhcuM`, "The Man Who Tried to Warn Google About AI | Tristan Harris",
  2:44. Recovered the existing draft after delayed ID exposure; no second transfer.
- Both Private / not made for kids, 15 tags each, original credits preserved.
  Ten long-form chapters preserved. Short description links to the long video.
  Both metadata and actual playback verified independently after publishing.
- New banner, insignia/avatar and watermark published and verified after reload.
  Existing channel name, handle and nonempty description retained. Assets and
  generation prompts: `branding/yousocial/`. Runtime evidence/URLs/logs:
  `uploads/yousocial/20261014_194800/` and `logs/`.
- Desktop Studio does not accept a custom image thumbnail for Shorts; uses a video
  frame. Adapter skips that image upload. Recovery handles Shorts tab, original
  filename titles, draft-only rows and Shorts-format URLs; waits for delayed IDs.
- This does not resolve the separate MoonSpot custom-thumbnail feature mismatch.

Last implementation commit before this context file: `403fb15` (branding and
thumbnail acceptance); preceding live trial fix: `37f6f1c`. These were pushed to
`origin/main`. Update this context when the thumbnail blocker is resolved.

## Short <-> explainer cross-linking (October 19, 2026)

Video Studio writes `Full breakdown: <PASTE LONG VIDEO LINK HERE>` into a Short's description only when the job made
both versions. `publisher_logic.link_short` resolves it: the explainer's published URL replaces the placeholder
(`linked`); a job with no explainer loses the line (`no_long`); an explainer that exists but is not published yet blocks
a single Short publish with a clear message (`needs_long`). `POST /publish/pair` (GUI: **Publish both**) publishes the
explainer first, waits for it to complete, injects its URL into the Short and then publishes the Short; if the explainer
fails the Short is not published. Tests: `tests/test_crosslink.py` (24 tests in all pass).
