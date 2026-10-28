# Verification — October 14, 2026

- Independent app launched at http://127.0.0.1:42030 through its PowerShell launcher.
- Logon task `Start YouTube Publisher` is registered with a 60-second delay and
  absolute working directory `F:\youtube-publisher`.
- 17 offline tests pass, including the eight inherited backend tests, range streaming,
  validation/credit preservation, draft isolation, thumbnail resizing, and preservation
  of publish success when linking fails.
- Real Chromium UI test passed: job preselection, both type tabs, Short-only disabled
  Explainer tab, native MP4 playback/scrubbing, metadata/chapters, draft saving, empty
  link list initially, populated link list after upload, desktop/mobile layouts, and
  no JavaScript errors. Edited `_edit_` video backups are excluded from selection.
- Headed Playwright live test uploaded job `20261013_023528` to MoonSpot as Private.
  Video ID: `aVqMNDA9Yyg`. Metadata, source credit and six chapters were sent; a
  landscape thumbnail was extracted from the finished video. `published.json`, URL,
  draft, automation state and step screenshots were saved under its publisher job.
- Independently reopened Studio and verified the title, Private visibility, and
  not-made-for-kids. Opened the watch page and confirmed actual playback advances.
  Final screenshots: `uploads/moonspots/20261013_023528/verified-studio.png` and
  `verified-watch.png` (excluded from Git along with all upload/profile data).
- Original `F:\youtube-uploads` remains unchanged with a clean Git working tree.
  Its old origin URL was preserved; GitHub redirects it following the repo rename.
- Video Studio still has a listener on 42020. No pipeline files/config/processes were
  changed or used by this app. Reference GUI source was read only during development.

## Deviations and remaining live coverage

- Source `publisher_logic.py` and `README.md` did not exist; both were created.
- The config key `moonspots` maps to the actual Studio display name **MoonSpot**,
  as verified in the account switcher. Matching remains exact and verified.
- No Phi-4/Ollama runtime was copied: that would conflict with the explicit isolation
  requirement. Metadata regeneration continues through the existing Codex backend.
- Error screenshots live in the publisher's upload/job folder, not the read-only
  Video Studio input job folder.
- End Screen linking has now passed the Moonshots live trial below. Shorts Related
  Video remains implemented with a manual fallback but has not been proved live.
  YouTube restricts Shorts related targets to eligible videos on the same channel.
  Records marked deleted are excluded locally; remote deletions are not synchronized.
- An earlier interrupted test for job `20261013_100822` remains **Pending** in Studio
  (`TfWacUL-m3s`). It is not recorded as a successful publish. It was retained rather
  than deleting a YouTube item without a request. Inspect it manually at
  https://studio.youtube.com/video/TfWacUL-m3s/edit before retrying that job.

Official feature references:
- https://support.google.com/youtube/answer/14075157
- https://support.google.com/youtube/answer/6388789

## Moonshots end-to-end trial — October 14, 2026

- Selected job `20261011_082753` from its log's Moonshots reference and source
  credits. Uploaded its finished 13:49 explainer to the verified **MoonSpot** channel:
  https://www.youtube.com/watch?v=iAkaTlE2__g (Private, not made for kids).
- Generated title/hook and 15 tags; preserved source credits and all 12 chapters.
  Selected a landscape thumbnail through the GUI, but subsequent checking found
  YouTube had not accepted it: MoonSpot requires phone verification for custom
  thumbnails. Source job files were read only.
- YouTube processing exceeded the old verification wait. Recovery now waits for
  persisted visibility up to the configured timeout and resumes the same video ID
  without uploading another copy. Exactly one video was uploaded for this trial.
- Adapted the current Editor introduction, video picker, frame-based timecodes and
  preview positioning. Saved a fixed end screen to the original public Moonshots
  episode `LRdb8UmPnh0`, at top-right from `13:33:02` to `13:48:02`.
  Reloaded Studio and verified target, timing and position. Private targets are
  rejected because YouTube can substitute them. YouTube hides end screens on the
  watch page while the uploaded video remains Private.
- Independently reopened Studio to verify title, Private and not-made-for-kids;
  confirmed actual watch-page playback advances. Evidence and URL are saved under
  `uploads/moonspots/20261011_082753/`; final linking task
  `a532874bdb6249698274494ac5007962` completed with no linking error.
- 19 offline tests pass, including frame preservation and invalid/short duration
  cases. Workflow events and step screenshots are retained in the job's task
  folder and `logs/publisher.log`. Reboot testing remains deferred by request.

## Branding and thumbnail acceptance correction

- Created a new AI's 1942 Moment thumbnail and matching MoonSpot banner, avatar
  and video watermark under `branding/moonspot/`, with generation prompts and
  channel copy. Published the banner, avatar, watermark and description; waited
  for Studio's Changes published confirmation and reloaded to verify persistence.
- Custom thumbnail selection alone was previously mistaken for acceptance.
  Clicking Upload file explicitly revealed YouTube's phone-verification gate.
  The upload adapter now requires a visible Uploaded thumbnail preview, otherwise
  stops with a clear message and preserves the existing upload for recovery.
- Existing video visibility remains Private. No new video was uploaded for branding.
- Saved all 15 channel keywords and verified them in reopened Channel settings.
  The final thumbnail attempt still requires the channel owner's phone verification.

## YouSocial live job — October 15, 2026

- Verified YouSocial / @ASocialSquare and all feature tiers Enabled.
- Job `20261014_194800`: long `UEpu0f1cBN4`, Short `HFSr6AnhcuM`.
  Both saved Private / not made for kids, 15 tags each; long has ten source chapters.
  Source attribution preserved; Short's placeholder replaced with the long URL.
- Independently reopened both: title/description, audience, visibility, tags and
  actual watch-page playback verified. Long uploaded-thumbnail preview persisted.
- Short recovery reused its existing draft after its ID was delayed and metadata
  had not autosaved. Exactly one transfer per asset. Added Shorts URL recognition,
  bounded ID waiting and recovery via Shorts tab/original filename/draft dialog.
- Desktop Shorts custom-image upload skipped; video-frame thumbnail retained.
- New banner, insignia and watermark published, then reloaded successfully.
  Existing description retained. Artwork/prompts in `branding/yousocial/`.
