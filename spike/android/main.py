"""Phase 2 spike: does ytmpd.core work inside a Flet APK? Runs every check at startup and shows the results.

Throwaway code: see DEVLOG.md for the answers.
"""

import os
import platform
import shutil
import sys
import time
from pathlib import Path

import flet as ft

URL = "https://www.youtube.com/playlist?list=UU4QobU6STFB0P71PMvOGN5A"  # "Me at the zoo", 19 s, public
SHARED_MUSIC = Path("/storage/emulated/0/Music/ytmpd-spike")


def main(page: ft.Page):
    page.title = "ytmpd spike"
    log = ft.ListView(expand=True, auto_scroll=True, spacing=4)
    page.add(ft.Text("ytmpd Android spike", size=20, weight=ft.FontWeight.BOLD), log)
    data = Path(os.getenv("FLET_APP_STORAGE_DATA") or ".")
    lines = []

    def say(msg):
        lines.append(msg)
        print("SPIKE", msg, flush=True)
        log.controls.append(ft.Text(msg, size=11, selectable=True))
        page.update()
        (data / "spike-report.txt").write_text("\n".join(lines), encoding="utf-8")

    def step(name, fn):
        start = time.time()
        try:
            say(f"OK   {name}: {fn()} ({time.time() - start:.1f}s)")
        except Exception as e:
            say(f"FAIL {name}: {type(e).__name__}: {str(e)[:300]}")

    def run():
        import yt_dlp
        from mutagen.mp4 import MP4

        from ytmpd import core

        say(f"python {sys.version.split()[0]}, {platform.machine()}, yt-dlp {yt_dlp.version.__version__}")
        step("JS runtimes on PATH", lambda: [n for n in ("deno", "node", "qjs", "bun") if shutil.which(n)] or "none")
        step("yt-dlp-ejs importable", lambda: __import__("yt_dlp_ejs") and "yes")
        step("ffmpeg on PATH", lambda: shutil.which("ffmpeg") or "none")
        step("list playlist", lambda: (lambda p: f"{p['title']}: {len(p['tracks'])} track(s)")(core.list_playlist(URL)))

        notes = []

        def on_event(e):
            if e["type"] in ("warning", "track_skipped"):
                notes.append(e.get("message") or e.get("reason"))

        out = data / "music"
        step("download m4a to app storage", lambda: core.download(URL, str(out), "m4a", on_event=on_event))
        for n in notes:
            say(f"     note: {n[:400]}")
        step("tags in the m4a", lambda: {k: v for k, v in MP4(next(out.glob("*.m4a"))).tags.items()})

        def copy_to_shared():
            SHARED_MUSIC.mkdir(parents=True, exist_ok=True)
            return shutil.copy(next(out.glob("*.m4a")), SHARED_MUSIC)

        step("copy m4a to shared Music/", copy_to_shared)
        step("write .txt to shared Music/", lambda: (SHARED_MUSIC / "archive-test.txt").write_text("x") and "written")
        step("download straight into shared Music/",
             lambda: core.download(URL, str(SHARED_MUSIC / "direct"), "m4a", on_event=on_event))
        say("DONE")

    page.run_thread(run)


ft.run(main)
