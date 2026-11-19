# Roadmap

From a command-line script to a GUI app for the desktop (Windows first, then macOS and Linux) and Android, with the
same features on both. The plan goes in phases; each one ends with something that works and can be released, and the
riskiest part (Android) is tested before the interface is built.

| Phase | Result | Platforms |
|---|---|---|
| [0. Stack](#phase-0--choose-the-stack) | One codebase in Python with Flet | |
| [1. Core](#phase-1--a-core-the-gui-can-call) ✅ | `downloader.py` split into a reusable core, the CLI keeps working | CLI |
| [2. Android spike](#phase-2--android-spike) ✅ | One track downloaded on a real phone, or a decision to change plan | Android |
| [3. Desktop MVP](#phase-3--desktop-mvp) ✅ | A window that does what the CLI does today, plus a track list | Windows |
| [4. Android app](#phase-4--android-app) 🚧 | The same app on the phone, with sharing from YouTube Music | Android |
| [5. Releases](#phase-5--builds-and-releases) ✅ | `.exe` and `.apk` built by GitHub Actions on every tag | Both |
| [6. Staying current](#phase-6--keeping-up-with-youtube) ✅ | A new build whenever yt-dlp changes | Both |
| [7. Later](#phase-7--later) ✅ | Covers, cleaner titles, playlist sync | Both |

## Phase 0 — Choose the stack

**Choice: [Flet](https://flet.dev), Python UI on top of Flutter.**

The work is done by yt-dlp, which is Python. Flet keeps the app in Python, so the core from phase 1 is imported as it
is, and `flet build windows` and `flet build apk` produce both apps from one codebase, with Material 3 widgets that
follow the system theme.

| Alternative | Why not |
|---|---|
| Kotlin app with [youtubedl-android](https://github.com/yausername/youtubedl-android) | Proven on Android (it bundles Python, yt-dlp and FFmpeg), but it means a second codebase for the desktop. It stays as the **fallback** if the phase 2 spike fails. |
| Capacitor, as in diario-yaz | The UI would be web, but yt-dlp still needs Python on the device: the hard part stays the same, with a JavaScript layer on top. |
| Kivy / BeeWare | Both build Python apps for Android, but Flet has the better widgets and the simpler build. |
| Electron or Tauri + the CLI | Desktop only. |

The Play Store does not accept apps that download from YouTube, so the APK is distributed through GitHub Releases, as in
diario-yaz.

## Phase 1 — A core the GUI can call

**Done.** Two things turned up along the way: the old script never wrote tags (`addmetadata` is a command-line
option of yt-dlp, ignored when called from Python), and forcing the `mweb` client now costs a warning per track
because it needs a PO Token, so the core lets yt-dlp choose its clients.

Today `downloader.py` prints to the terminal. A GUI needs functions that report events and can be stopped.

1. **Split the code** into a package:

   | Path | Contents |
   |---|---|
   | `ytmpd/core.py` | `normalize_url()`, `build_options()`, `list_playlist(url)`, `download(url, options, on_event, cancel)` |
   | `ytmpd/cli.py` | The current command line, now calling `core` |
   | `downloader.py` | Kept as a two-line wrapper, so the README commands still work |

2. **Events instead of prints**: `on_event` receives `track_started`, `progress` (percent, speed, ETA),
   `track_done`, `track_skipped` (with the reason) and `finished`. The CLI prints them, the GUI draws them.
3. **Cancel**: a `threading.Event` checked in the progress hook, which raises to stop yt-dlp cleanly.
4. **List before downloading**: `list_playlist()` uses `extract_flat` to return titles, durations and thumbnails in a
   few seconds, so the GUI can show the tracks and let you pick them.
5. **Remember what was downloaded**: yt-dlp's `download_archive` (one file per output folder). Running again on the
   same playlist downloads only the new tracks, which is also the base for playlist sync in phase 7.
6. **JavaScript runtime**: yt-dlp now needs one to solve YouTube's challenges, and only Deno is enabled by default.
   Switch to `yt-dlp[default]` (which brings `yt-dlp-ejs`) and pass `js_runtimes` explicitly; without it some
   formats are missing or downloads fail.
7. **Format choice**: MP3 (needs FFmpeg) or M4A, which is YouTube's own AAC stream saved as it is: no FFmpeg, no
   quality lost to re-encoding, tags written with `mutagen`.
8. **Tests**: `tests/test_core.py` for `normalize_url()` and `build_options()`, run with `python -m unittest`.

**Done when** the CLI downloads a playlist as before, a second run downloads nothing, and the tests pass.

## Phase 2 — Android spike

**Done** on the emulator (Android 16, x86_64); results in [DEVLOG.md](DEVLOG.md). Flet is confirmed: yt-dlp runs,
M4A downloads and is tagged without FFmpeg, and finished files can be copied into `Music/` with no permission. Still
open: a JavaScript runtime on Android (it works without one for now, but yt-dlp has deprecated that), and long
playlists with the screen off on a real phone.

A throwaway Flet app with one text field and one button, to answer the questions that decide whether the plan holds,
before any real UI is written.

| Question | What counts as yes | If no |
|---|---|---|
| Does yt-dlp run inside a Flet APK? | It lists a public playlist on the phone | Fallback: Kotlin + youtubedl-android |
| Is there a JavaScript runtime? | yt-dlp solves YouTube's challenge with QuickJS (or Deno) shipped in the APK | Fallback: Kotlin + youtubedl-android |
| Can the app run FFmpeg? | A static arm64 `ffmpeg` shipped in the APK converts one file | Android stays on M4A only, MP3 comes later |
| Where do files go? | The user picks a folder (e.g. `Music/`) and the file shows up in a music player | Save to the app's folder and share from there |
| Does a 50-track playlist finish with the screen off? | Yes, or it does with "keep screen on" | Accept "keep the app open" for v1; a foreground service goes to phase 7 |

Android 10 and later refuse to run executables from the app's data folder, so binaries such as `ffmpeg` and `qjs` have
to be packed as native libraries (`lib*.so`) and started from `nativeLibraryDir`, which is how youtubedl-android does
it. The spike has to find out whether Flet's build lets us do that.

**Done when** each row has an answer and the stack is confirmed or switched. Write the answers in a `DEVLOG.md`.

## Phase 3 — Desktop MVP

**Done.** `flet build windows` produces a 210 MB folder (85 MB zipped) that downloads and tags an MP3 on a PATH
without FFmpeg; see [DEVLOG.md](DEVLOG.md). Changes from the plan below: format, quality
and folder live on the Download screen (one place, remembered between runs) instead of Settings; FFmpeg comes from
the `imageio-ffmpeg` package; each playlist gets its own subfolder; HTTP 403s are retried once by the core.

| Screen | What is on it |
|---|---|
| **Download** | Link field (pasted from the clipboard when the window opens, if it is a YouTube link), **Load** button, the track list with checkboxes, format and quality, output folder, **Download** button. During the download: progress bar per track and overall, **Cancel** button. |
| **History** | Playlists downloaded, when, where, how many tracks, how many skipped and why. Opens the folder. |
| **Settings** | Default folder, format and quality, browser for cookies, language (Italian / English, like the CLI's messages), theme (system, light, dark). |

- The download runs in a background thread and sends events to the UI through Flet's `page.update()`; the window stays
  responsive and can be closed with a confirmation.
- FFmpeg ships with the app: a GUI user can't be asked to edit the PATH. A system FFmpeg still wins if present.
- Errors get plain messages: "this video is private", "sign in needed: choose a browser in Settings",
  "YouTube changed something: update the app".
- Colors from the logo (`#E0475B` as Material 3 seed), and the logo as the window icon.

**Done when** someone who has never opened a terminal downloads a playlist on Windows from a `.zip` or installer.

## Phase 4 — Android app

**Built and tested on the emulator**; see [DEVLOG.md](DEVLOG.md). Done: phone layout, M4A into `Music/`, `cookies.txt`
import, screen kept on, mobile data warning, QuickJS-ng shipped as `libqjs.so`, playlist links opened with the app.
The share sheet (item 1) came later, with the `ytmpd_android` extension: a Flet extension on top of the `receive_sharing_intent`
Flutter plugin, so no Kotlin of our own. Still open: a run on a real phone (long playlist, screen off) and the clipboard check, which the
emulator test couldn't drive.

The same screens, laid out for a phone (navigation bar at the bottom), plus what only makes sense on Android:

1. **Share from YouTube Music**: "Share → YT Music Playlist Downloader" opens the app with the link already filled in.
   This needs an intent filter for `text/plain` in the Android manifest; check how far Flet lets us customize it.
2. **Folder**: files go to `Music/` (or a subfolder), where Android accepts audio files without any permission.
   yt-dlp downloads into app storage and moves only the finished `.m4a` there (`paths` option); the archive stays in
   app storage, because `Music/` refuses non-audio files.
3. **Sign-in**: the browser's cookies can't be read on Android. v1: import a `cookies.txt` exported from a computer.
   Later: sign in to YouTube in a WebView inside the app and pass those cookies to yt-dlp.
4. **Long downloads**: a foreground service with a notification (`ytmpd_android`, on top of `flutter_foreground_task`);
   keeping the screen on is the fallback.
5. **Mobile data**: warning before downloading on a metered connection.
6. **JavaScript runtime**: ship a QuickJS binary for arm64 as a native library (`libqjs.so`) and pass its path in
   `js_runtimes`, so the app keeps working when yt-dlp drops extraction without a runtime.

**Done when** a playlist shared from the YouTube Music app ends up in the phone's music player.

## Phase 5 — Builds and releases

**Workflow in place**: [`release.yml`](.github/workflows/release.yml) runs the tests, builds the Windows zip and the
signed APK, and publishes both on a `v*` tag (a manual run builds without publishing). The signing key lives in the
`YTMPD_*` repository secrets; the APK is named after the version (`yt-music-playlist-downloader-0.2.0.apk`) rather
than the run number. The README has the **Download the app** section.
Verified on GitHub with manual runs: Windows (90 MB), macOS (83 MB), Linux (113 MB) and the signed APK (55 MB, same
certificate as v0.2.0). [v0.2.0](https://github.com/FrancescoPazz/yt-music-playlist-downloader/releases/tag/v0.2.0)
itself was built locally while Actions was blocked; see [DEVLOG.md](DEVLOG.md).

- `.github/workflows/build.yml`: on every `v*` tag, builds `yt-music-playlist-downloader-windows.zip` (and later
  macOS and Linux) and `yt-music-playlist-downloader-N.apk`, runs the tests first, and attaches the files to a GitHub
  Release.
- APK signed with a key kept in the repository secrets, never in the code, so every version installs over the
  previous one (same setup as diario-yaz).
- The README gets an **Install** section like diario-yaz's: where to download, what Android and Windows SmartScreen
  will say about an unknown app, and how updates work.

## Phase 6 — Keeping up with YouTube

**Done.** The weekly workflow hasn't had a new yt-dlp to react to yet. `bump_ytdlp.py` was tested
on a copy of the files with a pretend version, the update notice and the report against the real v0.2.0 release.
The report opens a prefilled GitHub issue as well as copying the text.

The app breaks when YouTube changes and yt-dlp hasn't caught up, and an app user can't run `pip install -U`.

- **Weekly workflow**: checks PyPI for a new yt-dlp, bumps `requirements.txt`, builds, and publishes a release if the
  tests pass.
- **Update check in the app**: at startup it reads the latest GitHub Release and shows "a new version is available"
  with a link. No auto-update.
- **"Report a problem"** button that copies the app version, yt-dlp version and the last error, ready to paste into an
  issue.

## Phase 7 — Later

**Done:** 1 (covers, with mutagen and Pillow, so also on Android), 2 (clean titles, kept simple: the original title
isn't stored), 3 (**Sync** on each History entry), 4 (a foreground service through the `ytmpd_android` extension,
no Kotlin of our own) and 5 (macOS and Linux jobs in `release.yml`).

1. **Cover art** embedded in the files (the video thumbnail, cropped square for YouTube Music tracks).
2. **Cleaner titles**: remove "(Official Video)", "[VISUALIZER]" and similar from file names and tags, with the
   original kept in the comment tag. Off by default.
3. **Sync a playlist**: re-check saved playlists and download only the new tracks (built on the phase 1 archive).
4. **Foreground service on Android**, so downloads continue with the app in the background.
5. **macOS and Linux builds** in the release workflow, once the Windows one is stable.

Not planned: iOS (Flet can build it, but distributing it outside the App Store isn't practical), and anything that gets around DRM or access checks.
