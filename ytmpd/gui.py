"""GUI for desktop and Android (Flet): Download, History and Settings. ytmpd.core does the work in a thread."""

import hashlib
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
COOKIES = DATA / "cookies.txt"
# Android (see DEVLOG, phase 2): only M4A (no FFmpeg), files end up in the shared Music folder, while partial files
# and the archive stay in app storage because Music/ refuses anything that isn't audio.
ANDROID_MUSIC = Path("/storage/emulated/0/Music/YT Music Playlist Downloader")
ANDROID_PARTIAL = DATA / "partial"
NAV = (
    (ft.Icons.DOWNLOAD_OUTLINED, ft.Icons.DOWNLOAD, "nav_download"),
    (ft.Icons.HISTORY_OUTLINED, ft.Icons.HISTORY, "nav_history"),
    (ft.Icons.SETTINGS_OUTLINED, ft.Icons.SETTINGS, "nav_settings"),
)


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


def link_from_route(route):
    """A YouTube link opened with the app arrives as a route like "/playlist?list=..."."""
    return f"https://www.youtube.com{route}" if route and "list=" in route else None


def open_folder(path):
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])


class App:
    def __init__(self, page: ft.Page):
        self.page = page
        self.mobile = page.platform.is_mobile()
        self.settings = DEFAULTS | load_json("settings.json", {})
        if self.mobile:
            self.settings |= {"folder": str(ANDROID_MUSIC), "format": "m4a"}
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
        self.wakelock = ft.Wakelock()
        self.connectivity = ft.Connectivity()

        page.title = "YT Music Playlist Downloader"
        page.window.width, page.window.height = 1000, 720
        page.window.min_width, page.window.min_height = 720, 520
        page.window.prevent_close = True
        page.window.on_event = self.on_window_event
        page.on_app_lifecycle_state_change = self.on_lifecycle
        page.on_route_change = lambda e: self.open_link(link_from_route(e.route))
        page.theme = ft.Theme(color_scheme_seed=SEED)
        page.dark_theme = ft.Theme(color_scheme_seed=SEED)
        self.apply_theme()
        self.render()
        # Not sys.argv: in the packaged app Flet's runner takes the first argument as the page URL.
        start_link = os.getenv("YTMPD_URL") or link_from_route(page.route)
        if start_link:
            self.open_link(start_link)
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

    def archive(self):
        out = self.output_dir()
        if not self.mobile:
            return core.archive_path(out)
        return DATA / "archives" / (hashlib.sha1(str(out).encode()).hexdigest()[:16] + ".txt")

    @staticmethod
    def cookies():
        return str(COOKIES) if COOKIES.is_file() else None

    @property
    def downloading(self):
        return self.cancel is not None

    # ---- layout --------------------------------------------------------------------------------------------

    def render(self):
        view = (self.download_view, self.history_view, self.settings_view)[self.tab]()
        if self.mobile:
            self.page.navigation_bar = ft.NavigationBar(
                selected_index=self.tab, on_change=self.on_tab,
                destinations=[ft.NavigationBarDestination(icon=i, selected_icon=s, label=self.t(k)) for i, s, k in NAV])
            self.page.controls[:] = [ft.SafeArea(ft.Container(view, padding=12, expand=True), expand=True)]
        else:
            rail = ft.NavigationRail(
                selected_index=self.tab, label_type=ft.NavigationRailLabelType.ALL, on_change=self.on_tab,
                destinations=[ft.NavigationRailDestination(icon=i, selected_icon=s, label=self.t(k)) for i, s, k in NAV])
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
            prefix_icon=ft.Icons.LINK, on_submit=self.load, disabled=self.downloading or self.loading,
            autofocus=not self.mobile,  # on a phone it would pop the keyboard over the list
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
        shown = str(self.output_dir()).removeprefix("/storage/emulated/0/")
        controls = [ft.Column([
            ft.Text(self.t("saves_to"), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text(f"M4A · {shown}", max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
        ], spacing=0, expand=True)] if self.mobile else [
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
        archived = core.archived_ids(self.archive())
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
        is_link = ("youtube.com/" in text or "youtu.be/" in text) and "\n" not in text
        # Replace only an empty field or an earlier link, never something the user is typing.
        if is_link and text != self.url and (not self.url or "youtu" in self.url) and not (
                self.loading or self.downloading):
            self.url = text
            if self.tab == 0:
                self.url_field.value = text
                self.url_field.update()

    def on_lifecycle(self, e):
        # Back from YouTube Music after "Share → Copy link": the link is waiting in the clipboard.
        if e.state == ft.AppLifecycleState.RESUME:
            self.page.run_task(self.prefill_from_clipboard)

    def open_link(self, url):
        if url and not (self.loading or self.downloading):
            self.url, self.tab = url, 0
            self.load()

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
            playlist = core.list_playlist(url, self.settings["browser"], self.cookies())
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

    async def start(self, e):
        tracks = [t for t in self.playlist["tracks"] if t["id"] in self.selected]
        if not tracks:
            return self.snack(self.t("nothing_selected"))
        if self.settings["format"] == "mp3" and not core.ffmpeg_available():
            return self.snack(self.t("no_ffmpeg"))
        if self.mobile and await self.on_mobile_data():
            def go(_):
                self.page.pop_dialog()
                self.begin(tracks)

            return self.page.show_dialog(ft.AlertDialog(
                title=ft.Text(self.t("mobile_data_title")), content=ft.Text(self.t("mobile_data_body")),
                actions=[ft.TextButton(self.t("cancel"), on_click=lambda _: self.page.pop_dialog()),
                         ft.FilledButton(self.t("mobile_data_go"), on_click=go)]))
        self.begin(tracks)

    async def on_mobile_data(self):
        try:
            kinds = await self.connectivity.get_connectivity()
        except Exception:
            return False
        return ft.ConnectivityType.MOBILE in kinds and not {ft.ConnectivityType.WIFI, ft.ConnectivityType.ETHERNET} & set(kinds)

    def begin(self, tracks):
        fmt = self.settings["format"]
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
        if self.mobile:  # a long playlist must not stop when the screen turns off
            self.page.run_task(self.wakelock.enable)
        self.page.run_thread(self.download_worker, items, fmt)

    def stop(self, e):
        self.cancel.set()
        self.render()

    def download_worker(self, items, fmt):
        out = self.output_dir()
        archive = self.archive()
        archive.parent.mkdir(parents=True, exist_ok=True)
        result = None
        try:
            result = core.download(self.playlist["url"], str(out), fmt, self.settings["bitrate"],
                                   self.settings["browser"], items, on_event=self.on_event, cancel=self.cancel,
                                   cookies=self.cookies(), temp_dir=str(ANDROID_PARTIAL) if self.mobile else None,
                                   archive=str(archive))
        except Exception as ex:
            self.last_line = self.t("download_failed", reason=self.reason(core.reason_kind(str(ex))))
        run, self.cancel = self.run, None
        if self.mobile:
            self.page.run_task(self.wakelock.disable)
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
        if kind in ("warning", "track_skipped"):  # to the console log (logcat on Android), for diagnosing
            print(f"ytmpd {kind}: {e.get('message') or e.get('reason')}", flush=True)
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
            ft.TextButton(self.t("open_folder"), icon=ft.Icons.FOLDER_OPEN, visible=not self.mobile,
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
        js = ", ".join(core.js_runtime_names()) or self.t("js_none")
        cookies_when = datetime.fromtimestamp(COOKIES.stat().st_mtime).strftime("%d/%m/%Y") if self.cookies() else None

        def section(title, *controls):
            return ft.Column([ft.Text(title, theme_style=ft.TextThemeStyle.TITLE_MEDIUM), *controls], spacing=8)

        browser = section(
            self.t("browser"),
            ft.Dropdown(value=self.settings["browser"], width=260, disabled=self.downloading,
                        options=[ft.DropdownOption(key=k, text=v) for k, v in browser_names.items()],
                        on_select=lambda e: self.set_setting("browser", e.control.value)),
            ft.Text(self.t("browser_help"), color=ft.Colors.ON_SURFACE_VARIANT))
        cookies = section(
            self.t("cookies_file"),
            ft.Text(self.t("cookies_loaded", when=cookies_when) if cookies_when else self.t("cookies_none")),
            ft.Row([
                ft.OutlinedButton(self.t("cookies_import"), icon=ft.Icons.UPLOAD_FILE, on_click=self.import_cookies,
                                  disabled=self.downloading),
                ft.TextButton(self.t("cookies_remove"), on_click=self.remove_cookies, visible=bool(cookies_when),
                              disabled=self.downloading),
            ], wrap=True),
            ft.Text(self.t("cookies_help"), color=ft.Colors.ON_SURFACE_VARIANT))
        return ft.ListView([
            *([] if self.mobile else [browser]),
            cookies,
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
                    ft.Text(self.t("about_ffmpeg", ffmpeg=ffmpeg), visible=not self.mobile),
                    ft.Text(self.t("about_js", js=js)),
                    ft.TextButton(self.t("repo"), icon=ft.Icons.OPEN_IN_NEW,
                                  on_click=lambda e: self.page.run_task(self.launcher.launch_url, REPO))),
        ], expand=True, spacing=28)

    async def import_cookies(self, e):
        files = await self.picker.pick_files(allowed_extensions=["txt"])
        if not files or not files[0].path:
            return
        try:
            text = Path(files[0].path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        # yt-dlp reads only the Netscape format: comment lines and tab-separated fields.
        if "\t" not in text or "youtube.com" not in text:
            return self.snack(self.t("cookies_invalid"))
        DATA.mkdir(parents=True, exist_ok=True)
        COOKIES.write_text(text, encoding="utf-8")
        self.snack(self.t("cookies_imported"))
        self.render()

    def remove_cookies(self, e):
        COOKIES.unlink(missing_ok=True)
        self.render()

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
