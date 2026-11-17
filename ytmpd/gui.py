"""Desktop GUI (Flet): Download, History and Settings. All the work is done by ytmpd.core in a background thread."""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import flet as ft
import yt_dlp
from yt_dlp.utils import sanitize_filename

from . import __version__, core
from .i18n import STRINGS, resolve_language

SEED = "#E0475B"
REPO = "https://github.com/FrancescoPazz/yt-music-playlist-downloader"
DATA = Path(os.getenv("FLET_APP_STORAGE_DATA") or Path.home() / ".ytmpd")
DEFAULTS = {
    "folder": str(Path.home() / "Music" / "YT Music Playlist Downloader"),
    "format": "mp3",
    "bitrate": "192",
    "browser": "none",
    "language": "auto",
    "theme": "system",
}
HISTORY_LIMIT = 100


def load_json(name, default):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8-sig"))  # -sig: tolerate a BOM from Notepad
    except (OSError, ValueError):
        return default


def save_json(name, value):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = DATA / (name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DATA / name)  # never leave a half-written file behind


def duration_text(seconds):
    if not seconds:
        return ""
    seconds = int(seconds)
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}" if seconds >= 3600 \
        else f"{seconds // 60}:{seconds % 60:02d}"


def open_folder(path):
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])


class App:
    def __init__(self, page: ft.Page):
        self.page = page
        self.settings = DEFAULTS | load_json("settings.json", {})
        self.history = load_json("history.json", [])
        self.lang = resolve_language(self.settings["language"])
        self.tab = 0
        self.url = ""
        self.playlist = None  # {"url", "title", "is_playlist", "tracks"}
        self.selected = set()  # video ids
        self.status = {}  # id -> "already" | "downloading" | "done" | ("skipped", kind, reason)
        self.percent = {}  # id -> 0..100
        self.loading = False
        self.cancel = None  # threading.Event while a download runs
        self.run = None  # counters of the running download
        self.last_line = ""  # result of the last load/download, shown under the list
        self.rows = {}  # id -> status Container, updated in place during downloads
        self.picker = ft.FilePicker()
        self.clipboard = ft.Clipboard()
        self.launcher = ft.UrlLauncher()

        page.title = "YT Music Playlist Downloader"
        page.window.width, page.window.height = 1000, 720
        page.window.min_width, page.window.min_height = 720, 520
        page.window.prevent_close = True
        page.window.on_event = self.on_window_event
        page.theme = ft.Theme(color_scheme_seed=SEED)
        page.dark_theme = ft.Theme(color_scheme_seed=SEED)
        self.apply_theme()
        self.render()
        if len(sys.argv) > 1:  # `python main.py LINK` (also "Open with" / share) loads it right away
            self.url = sys.argv[1]
            self.load()
        else:
            page.run_task(self.prefill_from_clipboard)

    # ---- helpers -------------------------------------------------------------------------------------------

    def t(self, key, **values):
        return STRINGS[self.lang][key].format(**values)

    def reason(self, kind):
        return self.t(f"reason_{kind}")

    def set_setting(self, key, value):
        self.settings[key] = value
        save_json("settings.json", self.settings)

    def apply_theme(self):
        self.page.theme_mode = {"light": ft.ThemeMode.LIGHT, "dark": ft.ThemeMode.DARK}.get(
            self.settings["theme"], ft.ThemeMode.SYSTEM)

    def snack(self, text):
        self.page.show_dialog(ft.SnackBar(ft.Text(text)))

    def output_dir(self):
        base = Path(self.settings["folder"])
        if self.playlist and self.playlist["is_playlist"]:
            return base / sanitize_filename(self.playlist["title"] or "YouTube")
        return base

    @property
    def downloading(self):
        return self.cancel is not None

    # ---- layout --------------------------------------------------------------------------------------------

    def render(self):
        rail = ft.NavigationRail(
            selected_index=self.tab,
            label_type=ft.NavigationRailLabelType.ALL,
            on_change=self.on_tab,
            destinations=[
                ft.NavigationRailDestination(icon=ft.Icons.DOWNLOAD_OUTLINED, selected_icon=ft.Icons.DOWNLOAD,
                                             label=self.t("nav_download")),
                ft.NavigationRailDestination(icon=ft.Icons.HISTORY_OUTLINED, selected_icon=ft.Icons.HISTORY,
                                             label=self.t("nav_history")),
                ft.NavigationRailDestination(icon=ft.Icons.SETTINGS_OUTLINED, selected_icon=ft.Icons.SETTINGS,
                                             label=self.t("nav_settings")),
            ],
        )
        view = (self.download_view, self.history_view, self.settings_view)[self.tab]()
        self.page.controls[:] = [
            ft.Row([rail, ft.VerticalDivider(width=1), ft.Container(view, expand=True, padding=20)], expand=True)
        ]
        self.page.update()

    def on_tab(self, e):
        self.tab = e.control.selected_index
        self.render()

    # ---- Download ------------------------------------------------------------------------------------------

    def download_view(self):
        self.url_field = ft.TextField(
            label=self.t("url_label"), hint_text=self.t("url_hint"), value=self.url, expand=True,
            prefix_icon=ft.Icons.LINK, on_submit=self.load, disabled=self.downloading or self.loading, autofocus=True,
            on_change=lambda e: setattr(self, "url", e.control.value),
        )
        top = ft.Row([
            self.url_field,
            ft.FilledButton(self.t("load"), icon=ft.Icons.QUEUE_MUSIC, on_click=self.load,
                            disabled=self.downloading or self.loading),
        ])
        return ft.Column([top, self.tracks_area(), self.bottom_bar()], expand=True, spacing=16)

    def tracks_area(self):
        if self.loading:
            return ft.Container(ft.Column([ft.ProgressRing(), ft.Text(self.t("loading"))],
                                          horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True),
                                expand=True, alignment=ft.Alignment.CENTER)
        if not self.playlist:
            return ft.Container(ft.Column([
                ft.Icon(ft.Icons.LIBRARY_MUSIC, size=56, color=ft.Colors.PRIMARY),
                ft.Text(self.t("empty_title"), theme_style=ft.TextThemeStyle.TITLE_MEDIUM),
                ft.Text(self.last_line or self.t("empty_body"), color=ft.Colors.ON_SURFACE_VARIANT,
                        text_align=ft.TextAlign.CENTER),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True), expand=True,
                alignment=ft.Alignment.CENTER)

        tracks = self.playlist["tracks"]
        header = ft.Row([
            ft.Column([
                ft.Text(self.playlist["title"] or "", theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(self.t("tracks_count_one" if len(tracks) == 1 else "tracks_count", n=len(tracks),
                               selected=len(self.selected)),
                        color=ft.Colors.ON_SURFACE_VARIANT),
            ], spacing=2, expand=True),
            ft.TextButton(self.t("select_all"), on_click=lambda e: self.select(True), disabled=self.downloading),
            ft.TextButton(self.t("select_none"), on_click=lambda e: self.select(False), disabled=self.downloading),
        ])
        self.rows = {}
        items = [self.track_row(track) for track in tracks]
        return ft.Column([header, ft.Container(
            ft.ListView(items, expand=True, spacing=0),
            expand=True, border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), border_radius=12,
        )], expand=True, spacing=8)

    def track_row(self, track):
        vid = track["id"]
        already = self.status.get(vid) == "already"
        status = ft.Container(self.status_icon(vid), width=28, alignment=ft.Alignment.CENTER)
        self.rows[vid] = status
        return ft.Container(ft.Row([
            ft.Checkbox(value=vid in self.selected and not already, disabled=self.downloading or already,
                        on_change=lambda e, vid=vid: self.toggle(vid, e.control.value)),
            ft.Text(f"{track['index']:03d}", font_family="Consolas", color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text(track["title"] or vid, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(duration_text(track["duration"]), color=ft.Colors.ON_SURFACE_VARIANT),
            status,
        ]), padding=ft.Padding.symmetric(horizontal=8))

    def status_icon(self, vid):
        state = self.status.get(vid)
        if state == "downloading":
            return ft.ProgressRing(value=(self.percent.get(vid) or 0) / 100, width=18, height=18, stroke_width=2.5)
        if state == "done":
            return ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.PRIMARY, size=20)
        if state == "already":
            return ft.Icon(ft.Icons.DOWNLOAD_DONE, color=ft.Colors.ON_SURFACE_VARIANT, size=20,
                           tooltip=self.t("already"))
        if isinstance(state, tuple):
            _, kind, reason = state
            return ft.Icon(ft.Icons.ERROR_OUTLINE, color=ft.Colors.ERROR, size=20,
                           tooltip=f"{self.reason(kind)}\n\n{reason}")
        return None

    def bottom_bar(self):
        fmt = self.settings["format"]
        controls = [
            ft.Dropdown(label=self.t("format"), value=fmt, width=210, disabled=self.downloading,
                        options=[ft.DropdownOption(key="mp3", text=self.t("format_mp3")),
                                 ft.DropdownOption(key="m4a", text=self.t("format_m4a"))],
                        on_select=lambda e: (self.set_setting("format", e.control.value), self.render())),
            ft.Dropdown(label=self.t("quality"), value=self.settings["bitrate"], width=150,
                        disabled=self.downloading or fmt != "mp3",
                        options=[ft.DropdownOption(key=b, text=f"{b} kbps") for b in core.BITRATES],
                        on_select=lambda e: self.set_setting("bitrate", e.control.value)),
            ft.Column([
                ft.Text(self.t("saves_to"), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(str(self.output_dir()), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                        tooltip=str(self.output_dir())),
            ], spacing=0, expand=True),
            ft.IconButton(ft.Icons.FOLDER_OPEN, tooltip=self.t("change_folder"), on_click=self.pick_folder,
                          disabled=self.downloading),
        ]
        if self.downloading:
            controls.append(ft.OutlinedButton(
                self.t("cancelling") if self.cancel.is_set() else self.t("cancel"), icon=ft.Icons.STOP,
                on_click=self.stop, disabled=self.cancel.is_set()))
        else:
            controls.append(ft.FilledButton(self.t("download"), icon=ft.Icons.DOWNLOAD, on_click=self.start,
                                            disabled=not self.playlist or self.loading))
        self.progress_bar = ft.ProgressBar(value=0, visible=self.downloading)
        self.progress_text = ft.Text(self.last_line, color=ft.Colors.ON_SURFACE_VARIANT,
                                     max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        return ft.Column([self.progress_bar, self.progress_text, ft.Row(controls)], spacing=8)

    def select(self, value):
        self.selected = {t["id"] for t in self.playlist["tracks"] if self.status.get(t["id"]) != "already"} \
            if value else set()
        self.render()

    def toggle(self, vid, value):
        (self.selected.add if value else self.selected.discard)(vid)
        self.render()

    async def pick_folder(self, e):
        path = await self.picker.get_directory_path(initial_directory=self.settings["folder"])
        if path:
            self.set_setting("folder", path)
            self.mark_archived()
            self.render()

    def mark_archived(self):
        """Tracks already in the target folder's archive are shown as done and left unselected."""
        if not self.playlist:
            return
        archived = core.archived_ids(self.output_dir())
        for track in self.playlist["tracks"]:
            vid = track["id"]
            if vid in archived and self.status.get(vid) != "done":  # keep this session's check marks
                self.status[vid] = "already"
                self.selected.discard(vid)
            elif self.status.get(vid) == "already":
                del self.status[vid]

    async def prefill_from_clipboard(self):
        try:
            text = (await self.clipboard.get() or "").strip()
        except Exception:
            return
        if not self.url and ("youtube.com/" in text or "youtu.be/" in text) and "\n" not in text:
            self.url = text
            if self.tab == 0 and not self.loading:
                self.url_field.value = text
                self.url_field.update()

    # ---- loading and downloading (background threads) ------------------------------------------------------

    def load(self, e=None):
        url = self.url.strip()
        if not url or self.loading or self.downloading:
            return
        self.loading, self.last_line = True, ""
        self.render()
        self.page.run_thread(self.load_worker, url)

    def load_worker(self, url):
        try:
            playlist = core.list_playlist(url, self.settings["browser"])
        except Exception as ex:
            self.playlist = None
            self.last_line = self.t("load_failed", reason=self.reason(core.reason_kind(str(ex))))
        else:
            self.playlist = playlist | {"url": url}
            self.status, self.percent = {}, {}
            self.selected = {t["id"] for t in playlist["tracks"]}
            self.mark_archived()
        finally:
            self.loading = False
            self.render()

    def start(self, e):
        tracks = [t for t in self.playlist["tracks"] if t["id"] in self.selected]
        if not tracks:
            return self.snack(self.t("nothing_selected"))
        fmt = self.settings["format"]
        if fmt == "mp3" and not core.ffmpeg_available():
            return self.snack(self.t("no_ffmpeg"))
        pending = [t for t in self.playlist["tracks"] if self.status.get(t["id"]) != "already"]
        # Only pass the positions when some new tracks were left out: archived ones are skipped anyway.
        items = None if len(tracks) == len(pending) else ",".join(str(t["index"]) for t in tracks)
        for t in tracks:
            self.status.pop(t["id"], None)
        self.cancel = threading.Event()
        self.run = {"total": len(tracks), "n": 0, "done": 0, "skipped": {}, "started": set(), "current": None, "last_draw": 0.0,
                    "titles": {t["id"]: t["title"] for t in tracks}}
        self.last_line = ""
        self.render()
        self.page.run_thread(self.download_worker, items, fmt)

    def stop(self, e):
        self.cancel.set()
        self.render()

    def download_worker(self, items, fmt):
        out = self.output_dir()
        result = None
        try:
            result = core.download(self.playlist["url"], str(out), fmt, self.settings["bitrate"],
                                   self.settings["browser"], items, on_event=self.on_event, cancel=self.cancel)
        except Exception as ex:
            self.last_line = self.t("download_failed", reason=self.reason(core.reason_kind(str(ex))))
        run, self.cancel = self.run, None
        if result:
            key = "cancelled" if result["cancelled"] else "finished"
            self.last_line = self.t(key, done=run["done"], skipped=len(run["skipped"]))
        self.history.insert(0, {
            "url": self.playlist["url"], "title": self.playlist["title"], "folder": str(out),
            "when": datetime.now().isoformat(timespec="minutes"), "format": fmt,
            "done": run["done"], "skipped": list(run["skipped"].values()),
        })
        del self.history[HISTORY_LIMIT:]
        save_json("history.json", self.history)
        self.mark_archived()
        self.render()

    def on_event(self, e):
        run, kind = self.run, e["type"]
        vid = e.get("id") or run["current"]
        if kind == "track_started":
            run["skipped"].pop(vid, None)  # a retry after a 403 clears the earlier failure
            if vid not in run["started"]:
                run["started"].add(vid)
                run["n"] += 1
            run["current"] = vid
            self.status[vid], self.percent[vid] = "downloading", 0
            self.progress_text.value = self.t("progress", n=run["n"], total=run["total"], title=e["title"] or "")
        elif kind == "progress":
            self.percent[vid] = e["percent"] or 0
            if time.monotonic() - run["last_draw"] < 0.2:  # a few redraws per second are plenty
                return
        elif kind == "track_done":
            run["done"] += 1
            self.status[vid] = "done"
        elif kind == "track_skipped":
            if vid not in run["started"]:
                run["started"].add(vid)
                run["n"] += 1
            self.status[vid] = ("skipped", e["kind"], e["reason"])
            run["skipped"][vid] = {"title": run["titles"].get(vid) or e.get("title") or vid or "?", "kind": e["kind"]}
        else:
            return
        run["last_draw"] = time.monotonic()
        finished = run["done"] + len(run["skipped"])
        current = self.percent.get(run["current"], 0) / 100 if self.status.get(run["current"]) == "downloading" else 0
        self.progress_bar.value = min(1, (finished + current) / run["total"])
        if vid in self.rows:
            self.rows[vid].content = self.status_icon(vid)
        self.page.update()

    # ---- History -------------------------------------------------------------------------------------------

    def history_view(self):
        if not self.history:
            return ft.Container(ft.Column([
                ft.Icon(ft.Icons.HISTORY, size=56, color=ft.Colors.PRIMARY),
                ft.Text(self.t("history_empty"), color=ft.Colors.ON_SURFACE_VARIANT),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True), expand=True,
                alignment=ft.Alignment.CENTER)
        return ft.ListView([self.history_card(h) for h in self.history], expand=True, spacing=12)

    def history_card(self, h):
        when = datetime.fromisoformat(h["when"]).strftime("%d/%m/%Y %H:%M")
        lines = [
            ft.Text(h["title"] or h["url"], theme_style=ft.TextThemeStyle.TITLE_MEDIUM, max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(f"{when} · {h['format'].upper()} · {h['folder']}", color=ft.Colors.ON_SURFACE_VARIANT,
                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(self.t("history_summary", done=h["done"], skipped=len(h["skipped"]))),
        ]
        lines += [ft.Text(f"• {s['title']}: {self.reason(s['kind'])}", size=12, color=ft.Colors.ERROR)
                  for s in h["skipped"][:5]]
        if len(h["skipped"]) > 5:
            lines.append(ft.Text(f"• … +{len(h['skipped']) - 5}", size=12, color=ft.Colors.ERROR))
        actions = ft.Row([
            ft.TextButton(self.t("open_folder"), icon=ft.Icons.FOLDER_OPEN,
                          on_click=lambda e, f=h["folder"]: open_folder(f), disabled=not Path(h["folder"]).is_dir()),
            ft.TextButton(self.t("load_again"), icon=ft.Icons.REFRESH,
                          on_click=lambda e, u=h["url"]: self.load_again(u), disabled=self.downloading),
        ])
        return ft.Container(ft.Column(lines + [actions], spacing=4), padding=16, border_radius=12,
                            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW)

    def load_again(self, url):
        self.url, self.tab = url, 0
        self.load()

    # ---- Settings ------------------------------------------------------------------------------------------

    def settings_view(self):
        browser_names = {"none": self.t("browser_none")} | {b: b.capitalize() for b in core.BROWSERS[1:]}
        ffmpeg = self.t("ffmpeg_system") if shutil.which("ffmpeg") else \
            self.t("ffmpeg_bundled") if core.bundled_ffmpeg() else self.t("ffmpeg_missing")
        js = ", ".join(n for n in ("deno", "node", "qjs", "bun") if shutil.which(n)) or self.t("js_none")

        def section(title, *controls):
            return ft.Column([ft.Text(title, theme_style=ft.TextThemeStyle.TITLE_MEDIUM), *controls], spacing=8)

        return ft.ListView([
            section(self.t("browser"),
                    ft.Dropdown(value=self.settings["browser"], width=260, disabled=self.downloading,
                                options=[ft.DropdownOption(key=k, text=v) for k, v in browser_names.items()],
                                on_select=lambda e: self.set_setting("browser", e.control.value)),
                    ft.Text(self.t("browser_help"), color=ft.Colors.ON_SURFACE_VARIANT)),
            section(self.t("language"),
                    ft.Dropdown(value=self.settings["language"], width=260,
                                options=[ft.DropdownOption(key="auto", text=self.t("language_auto")),
                                         ft.DropdownOption(key="it", text="Italiano"),
                                         ft.DropdownOption(key="en", text="English")],
                                on_select=self.on_language)),
            section(self.t("theme"),
                    ft.Dropdown(value=self.settings["theme"], width=260,
                                options=[ft.DropdownOption(key=k, text=self.t(f"theme_{k}"))
                                         for k in ("system", "light", "dark")],
                                on_select=self.on_theme)),
            section(self.t("about"),
                    ft.Text(self.t("about_versions", app=__version__, ytdlp=yt_dlp.version.__version__)),
                    ft.Text(self.t("about_ffmpeg", ffmpeg=ffmpeg)),
                    ft.Text(self.t("about_js", js=js)),
                    ft.TextButton(self.t("repo"), icon=ft.Icons.OPEN_IN_NEW,
                                  on_click=lambda e: self.page.run_task(self.launcher.launch_url, REPO))),
        ], expand=True, spacing=28)

    def on_language(self, e):
        self.set_setting("language", e.control.value)
        self.lang = resolve_language(e.control.value)
        self.render()

    def on_theme(self, e):
        self.set_setting("theme", e.control.value)
        self.apply_theme()
        self.page.update()

    # ---- closing -------------------------------------------------------------------------------------------

    async def on_window_event(self, e):
        if e.type != ft.WindowEventType.CLOSE:
            return
        if not self.downloading:
            await self.page.window.destroy()
            return

        async def close(_):
            self.cancel.set()
            await self.page.window.destroy()

        self.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text(self.t("close_title")), content=ft.Text(self.t("close_body")),
            actions=[ft.TextButton(self.t("close_keep"), on_click=lambda _: self.page.pop_dialog()),
                     ft.FilledButton(self.t("close_confirm"), on_click=close)],
        ))


def main(page: ft.Page):
    App(page)
