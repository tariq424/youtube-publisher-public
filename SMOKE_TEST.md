# Moonspots smoke test — 2026-10-13

Command: .\publish-youtube.ps1 -Job 20261013_023528 -Channel Moonspots -Upload

Result: stopped before Chrome or metadata generation with exit code 1:

Chrome profile for channel Moonspots not found at F:\youtube-uploads\profiles\moonspots. Log into YouTube in that profile first.

No upload occurred and no YouTube URL was created. The profile requires the user's
one-time login. The actual requested job output was inspected: it contains an
explainer MP4, SRT and youtube_description.txt, but no thumbnail. Supply a thumbnail
with -Thumbnail when retesting. No pipeline or job inputs were modified.

Seven offline tests pass, including all five retained original tests.
Local workflow log: logs\workflow.log (excluded from Git).
