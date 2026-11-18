# Devlog

## 2026-11-18 — Phase 7, and the release workflow on GitHub

- With Actions unblocked, manual runs of `release.yml` built every platform. The APK from CI is signed with the release
  certificate (`4720a0ca…`) and has versionCode 3, above v0.2.0's 2, so it installs as an update.
- The first macOS run failed in `version.sh`: macOS's BSD `sed -i` wants a suffix; `sed -i.bak … && rm *.bak` works
  with both seds. Linux needed nothing beyond Flet's own apt list (`flet_cli.utils.linux_deps`).
- Covers: `hqdefault.jpg` is 480x360 with the 16:9 picture between black bands; cutting the bands before the square
  crop keeps them out (tested). "Me at the zoo" has no `maxresdefault.jpg`, so the fallback was exercised live: MP3
  and M4A both got a 270x270 cover, the MP3 still in ID3v2.3.
- Clean titles: the first rule for endings like " - Official Video" also matched inside "(Girls Trip - Official
  Visualizer)" and left a bracket open; endings now can't contain brackets.
- Sync, run twice through the GUI logic: the first downloaded the track, the second said there was nothing new.
- Not done: downloads in the background on Android (item 4); it needs a Kotlin foreground service.

## 2026-11-18 — Phase 6: keeping up with YouTube

- `yt-dlp-update.yml` (Mondays) runs `.github/scripts/bump_ytdlp.py`. With `--latest 2026.11.10 --ejs 0.8.1` on a copy of
  the files it raised yt-dlp in `requirements.txt`, `pyproject.toml` and the README badges, set the Android
  `yt-dlp-ejs` pin to the one yt-dlp asks for, bumped the app to 0.2.1 and printed `v0.2.1`; against PyPI
  (still 2026.10.26) it changed nothing.
- A tag pushed with `GITHUB_TOKEN` doesn't start other workflows, so the update workflow starts `release.yml` itself
  with `gh workflow run --ref <tag>`; on that ref `github.ref` is the tag, so the release job runs.
- The app asks `api.github.com/repos/…/releases/latest` once at startup, in a thread, with certifi's CA bundle (Android's
  Python has no system one). Run from source as 0.1.0, it showed "Version v0.2.0 is available" with a Download button.
- **Report a problem** builds the report without any link (a playlist can be private) and opens
  `issues/new?title=…&body=…`; with two errors the URL is about 450 characters.

## 2026-11-18 — Phase 5: release workflow and v0.2.0

- `release.yml` is written but has not run yet: GitHub refuses to start any job ("your account is locked due to a
  billing issue"), both for the manual run and for tag `v0.2.0`.
- v0.2.0 was therefore built on the maintainer's PC from the tag, with the same versions as the workflow
  (`--build-version 0.2.0 --build-number 2`) and the release key: `apksigner` shows the certificate
  `CN=YT Music Playlist Downloader`, SHA-256 `4720a0ca…815914`, versionCode 2. The next build from the workflow must
  use a higher build number; GitHub's run numbers for this workflow start at 3, so they do.
- The first local APK build failed with the JVM out of memory (Gradle asks for 8 GB) while the emulator was running;
  closing the emulator was enough.
- Re-running workflow run 2 (tag `v0.2.0`) would now fail at the last step, because the release already exists.

## 2026-11-18 — Phase 4: Android app

Same `ytmpd/gui.py` as the desktop, switching on `page.platform.is_mobile()`. Built with
`flet build apk --arch arm64-v8a x86_64` (54 MB) and tested on the emulator (Android 16, x86_64).

### What works, and how it was checked

| Feature | Check |
|---|---|
| Opening a playlist link with the app | `am start -a VIEW -d https://music.youtube.com/playlist?list=…`: the app opens with the playlist loaded (Flet passes the link as the route `/playlist?list=…`). |
| Phone layout | Navigation bar at the bottom, no format/folder controls, no browser cookies; screenshots in `docs/screenshots`. |
| M4A into `Music/` | yt-dlp's `paths` downloads and tags in app storage and moves only the finished file: `Music/YT Music Playlist Downloader/Uploads from jawed/` holds just the `.m4a`; the archive stays in app storage. |
| QuickJS | `qjs` from quickjs-ng 0.18.0, cross-compiled with NDK r28 and shipped as `ytmpd_qjs/libqjs.so` in a wheel per ABI. Flet's packaging copies any plain `.so` of an installed package into `jniLibs`, and `legacy_packaging = true` extracts it to `ANDROID_NATIVE_LIBRARY_DIR`, where it can run. Settings shows "quickjs"; the download log no longer has the "No supported JavaScript runtime" warning of phase 2. |
| Screen kept on | `dumpsys window` shows `KEEP_SCREEN_ON` during the download and not after. |
| Mobile data warning | With Wi-Fi off, Download asks first; "Download anyway" saves the file. |

### Findings

- Flet's Android activity is a bare `FlutterFragmentActivity`: an intent filter for `SEND` can be declared in
  `pyproject.toml`, but nothing hands `EXTRA_TEXT` to Python. Real sharing needs a Flet extension with Kotlin code.
- Every `subprocess` launch logs `libsigchain: Setting SIGSEGV to SIG_DFL` with a stack trace: it's the child
  resetting its signal handlers, not a crash.
- The emulator shell has no clipboard command and its clipboard is synced with the host's, so the clipboard check on
  resume wasn't tested automatically.
- `cookies.txt` import wasn't tested on the emulator (it needs the system file picker); its code is shared with the
  desktop app.

## 2026-11-18 — Phase 3: desktop app

The Flet app (`main.py`, `ytmpd/gui.py`) was tested three ways: a script driving `App` with a fake page and real
downloads, the window run from source with screenshots, and the packaged `.exe` from `flet build windows`.

### What the tests found

| Found | Fix |
|---|---|
| YouTube sometimes answers the first download with HTTP 403; five downloads in a row then worked. | `core.download()` runs a second pass for 403s only; the archive skips the tracks already done. |
| A 403 message has no video id, so the GUI didn't know which row failed and history saved `null` as title. | A `pre_process` postprocessor remembers the video being processed; errors without an id are attributed to it. |
| `settings.json` written by Windows PowerShell 5.1 starts with a BOM and failed to load, silently resetting the settings. | Read with `utf-8-sig`. |
| A link to a missing playlist showed "Unexpected error". | New reason kind `not_found`. |
| In the packaged app, a command-line argument leaves the window blank. Flet's runner uses `args[0]` as the page URL and never starts Python. | The startup link comes from the `YTMPD_URL` environment variable instead of `sys.argv`. |

### Windows build notes

- Needs Visual Studio Build Tools 2022 (C++ desktop workload) and Developer Mode. Developer Mode was off again
  by the time of the Windows build, after working for the Android one; check `AllowDevelopmentWithoutDevLicense` under
  `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock` if Flutter asks for it again. PowerShell 5.1's
  `New-Item -ItemType SymbolicLink` needs admin even with Developer Mode; `cmd /c mklink` is the right test.
- Output: `build/windows`, 210 MB (Python 3.14, yt-dlp, the 100 MB FFmpeg from `imageio-ffmpeg`); 85 MB zipped.
- The first start after a build takes 25–40 s while Python unpacks; later starts show the UI in about 3 s.
- The packaged app keeps its data in `%APPDATA%\Francesco Pazzaglia\YT Music Playlist Downloader\data`
  (`FLET_APP_STORAGE_DATA`) and its Python console in `%LOCALAPPDATA%\Francesco Pazzaglia\YT Music Playlist Downloader\console.log`.
- Faking the user folder (`USERPROFILE`) to keep test files out of the real one breaks the packaged app
  (`MissingPlatformDirectoryException`); point the download folder in `settings.json` somewhere else instead.

## 2026-11-17 — Phase 2: Android spike

A throwaway Flet app ([`spike/android/main.py`](spike/android/main.py)) that imports `ytmpd.core` and runs every check
at startup. Built with Flet 1.1.2 (`flet build apk --arch arm64-v8a x86_64`), run on the Android Studio emulator:
Android 16 (API 36.1), x86_64, Google Play image. Test video: "Me at the zoo" (19 s, public), through its channel's
uploads playlist.

### Answers

| Question | Answer | Evidence |
|---|---|---|
| Does yt-dlp run inside a Flet APK? | **Yes.** | Python 3.14.10 and yt-dlp 2026.10.26 start; `list_playlist()` returns the track in 2.3 s. |
| Is there a JavaScript runtime? | **No, and today it still works without one.** | `download()` finishes in 3.5 s, but yt-dlp warns that extraction without a JS runtime is deprecated and some formats may be missing. `yt-dlp-ejs` is installed; it just has nothing to run on. |
| Can the app run FFmpeg? | **Not needed for v1.** Bundling it was not tried. | M4A works without it: the file is tagged by `Mp4Tags` (title, artist). yt-dlp warns that it wrote a "DASH m4a", but Android's MediaStore reads it fine: duration 19 064 ms, `audio/mp4`, title and artist from the tags. |
| Where do files go? | **Download to app storage, then copy into `Music/`.** No permission needed. | `shutil.copy` of the `.m4a` into `/storage/emulated/0/Music/ytmpd-spike/` works and the file shows up in MediaStore owned by the app. Writing a `.txt` there fails with `PermissionError: [Errno 1] Operation not permitted`. Downloading straight into `Music/` leaves nothing, most likely because yt-dlp's `.part` temp file is refused the same way. |
| Does a 50-track playlist finish with the screen off? | **Not tested.** | Needs a real phone and a real playlist. |

### Decisions

- **Stack confirmed: Flet.** No need for the Kotlin fallback.
- **Android v1 is M4A only.** MP3 on Android waits until someone needs it; then try a static `ffmpeg` packed as
  `libffmpeg.so` with `--android-legacy-packaging`.
- **Storage layout on Android:** yt-dlp's `paths` option (`{"temp": <app storage>, "home": <Music folder>}`) downloads
  and tags in app storage and moves only the finished `.m4a` into `Music/`. The archive file stays in app storage.
  `core.download()` needs two new optional arguments for this (`temp_dir`, `archive`); do it in phase 4.
- **JS runtime is the main open risk.** It works now, but yt-dlp has deprecated the no-runtime path. Before phase 4:
  try a QuickJS binary for arm64 packed as a native library, and enable `quickjs` with its path.

### Build notes

- Windows needs **Developer Mode** on (Settings → System → For developers): Flutter's plugin build uses symlinks.
- The first build downloads Flutter 3.47.9, Python 3.14 for Android and the Android cmdline-tools; Gradle took 11
  minutes the first time.
- `flet build` crashed at the very end while logging Flutter's "√ Built" line to a file in cp1252, after the APK was
  already written. Run it with `PYTHONUTF8=1` to avoid it.
- The APK is 112 MB with two ABIs; `--split-per-abi` will roughly halve each download.
- Packages: only pure-Python ones (`yt-dlp`, `yt-dlp-ejs`, `mutagen`, `requests`, `certifi`). The native extras of
  `yt-dlp[default]` (brotli, pycryptodomex, websockets) were left out and YouTube doesn't need them.
- The emulator reloaded its boot snapshot once and wiped the installed APK; reinstall if `pm list packages` doesn't
  show it.

### Reproduce

```bash
cp -r ytmpd spike/android/ytmpd          # the build only packages the app folder
cd spike/android
PYTHONUTF8=1 ../../.venv/Scripts/flet build apk --arch arm64-v8a x86_64 --yes
adb install -r build/flutter/build/app/outputs/flutter-apk/app-release.apk
adb logcat | grep SPIKE                  # results, also shown on screen
```
