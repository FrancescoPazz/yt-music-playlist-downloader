# Roadmap

From a command-line script to a GUI app for the desktop (Windows first, then macOS and Linux) and Android, with the
same features on both. The plan goes in phases; each one ends with something that works and can be released, and the
riskiest part (Android) is tested before the interface is built.

| Phase | Result | Platforms |
|---|---|---|
| [0. Stack](#phase-0--choose-the-stack) | One codebase in Python with Flet | |
| [1. Core](#phase-1--a-core-the-gui-can-call) | `downloader.py` split into a reusable core, the CLI keeps working | CLI |
| [2. Android spike](#phase-2--android-spike) | One track downloaded on a real phone, or a decision to change plan | Android |
| [3. Desktop MVP](#phase-3--desktop-mvp) | A window that does what the CLI does today, plus a track list | Windows |
| [4. Android app](#phase-4--android-app) | The same app on the phone, with sharing from YouTube Music | Android |
| [5. Releases](#phase-5--builds-and-releases) | `.exe` and `.apk` built by GitHub Actions on every tag | Both |
| [6. Staying current](#phase-6--keeping-up-with-youtube) | A new build whenever yt-dlp changes | Both |
| [7. Later](#phase-7--later) | Covers, cleaner titles, playlist sync | Both |

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

A throwaway Flet app with one text field and one button, to answer the questions that decide whether the plan holds,
before any real UI is written.

| Question | What counts as yes | If no |
|---|---|---|
| Does yt-dlp run inside a Flet APK? | It lists a public playlist on the phone | Fallback: Kotlin + youtubedl-android |
| Is there a JavaScript runtime? | yt-dlp solves YouTube's challenge with QuickJS (or Deno) shipped in the APK | Try `mweb`-only formats; otherwise fallback |
| Can the app run FFmpeg? | A static arm64 `ffmpeg` shipped in the APK converts one file | Android stays on M4A only, MP3 comes later |
| Where do files go? | The user picks a folder (e.g. `Music/`) and the file shows up in a music player | Save to the app's folder and share from there |
| Does a 50-track playlist finish with the screen off? | Yes, or it does with "keep screen on" | Accept "keep the app open" for v1; a foreground service goes to phase 7 |

Android 10 and later refuse to run executables from the app's data folder, so binaries such as `ffmpeg` and `qjs` have
to be packed as native libraries (`lib*.so`) and started from `nativeLibraryDir`, which is how youtubedl-android does
it. The spike has to find out whether Flet's build lets us do that.

**Done when** each row has an answer and the stack is confirmed or switched. Write the answers in a `DEVLOG.md`.

## Phase 3 — Desktop MVP

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

The same screens, laid out for a phone (navigation bar at the bottom), plus what only makes sense on Android:

1. **Share from YouTube Music**: "Share → YT Music Playlist Downloader" opens the app with the link already filled in.
   This needs an intent filter for `text/plain` in the Android manifest; check how far Flet lets us customize it.
2. **Folder**: chosen once with the system picker and remembered; files appear in music players.
3. **Sign-in**: the browser's cookies can't be read on Android. v1: import a `cookies.txt` exported from a computer.
   Later: sign in to YouTube in a WebView inside the app and pass those cookies to yt-dlp.
4. **Long downloads**: keep the screen on during the download (or the foreground service, if phase 2 found a way).
5. **Mobile data**: warning before downloading on a metered connection.

**Done when** a playlist shared from the YouTube Music app ends up in the phone's music player.

## Phase 5 — Builds and releases

- `.github/workflows/build.yml`: on every `v*` tag, builds `yt-music-playlist-downloader-windows.zip` (and later
  macOS and Linux) and `yt-music-playlist-downloader-N.apk`, runs the tests first, and attaches the files to a GitHub
  Release.
- APK signed with a key kept in the repository secrets, never in the code, so every version installs over the
  previous one (same setup as diario-yaz).
- The README gets an **Install** section like diario-yaz's: where to download, what Android and Windows SmartScreen
  will say about an unknown app, and how updates work.

## Phase 6 — Keeping up with YouTube

The app breaks when YouTube changes and yt-dlp hasn't caught up, and an app user can't run `pip install -U`.

- **Weekly workflow**: checks PyPI for a new yt-dlp, bumps `requirements.txt`, builds, and publishes a release if the
  tests pass.
- **Update check in the app**: at startup it reads the latest GitHub Release and shows "a new version is available"
  with a link. No auto-update.
- **"Report a problem"** button that copies the app version, yt-dlp version and the last error, ready to paste into an
  issue.

## Phase 7 — Later

1. **Cover art** embedded in the files (the video thumbnail, cropped square for YouTube Music tracks).
2. **Cleaner titles**: remove "(Official Video)", "[VISUALIZER]" and similar from file names and tags, with the
   original kept in the comment tag. Off by default.
3. **Sync a playlist**: re-check saved playlists and download only the new tracks (built on the phase 1 archive).
4. **Foreground service on Android**, so downloads continue with the app in the background.
5. **macOS and Linux builds** in the release workflow, once the Windows one is stable.

Not planned: iOS (Flet can build it, but distributing it outside the App Store isn't practical), and anything that gets around DRM or access checks.
