"""Download a YouTube / YouTube Music playlist as MP3 or M4A.

Nothing here prints: progress is reported as event dicts to `on_event`, so the CLI and the GUI can draw it their way.
Use only for content you are authorized to download.
"""

import shutil
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yt_dlp
from yt_dlp.postprocessor import PostProcessor
from yt_dlp.utils import DownloadCancelled

BROWSERS = ("none", "chrome", "edge", "firefox", "brave", "opera", "vivaldi")
FORMATS = ("mp3", "m4a")
BITRATES = ("128", "192", "256", "320")
ARCHIVE = ".ytmpd-archive.txt"
# yt-dlp needs a JavaScript runtime for YouTube and enables only Deno by default.
# Enabling all of them lets it use whichever is installed (priority: deno, node, quickjs, bun).
JS_RUNTIMES = {"deno": {}, "node": {}, "quickjs": {}, "bun": {}}


def normalize_url(url: str) -> str:
    """Any youtube.com / music.youtube.com link with list= becomes the plain playlist link."""
    parsed = urlparse(url)
    playlist_id = parse_qs(parsed.query).get("list", [None])[0]
    if playlist_id and parsed.netloc in {"music.youtube.com", "www.youtube.com", "youtube.com", "m.youtube.com"}:
        return f"https://www.youtube.com/playlist?list={playlist_id}"
    return url


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _base_options(browser: str) -> dict:
    opts = {
        "quiet": True,
        "noprogress": True,
        "js_runtimes": JS_RUNTIMES,
    }
    if browser != "none":
        opts["cookiesfrombrowser"] = (browser,)
    return opts


def build_options(output_dir: str, fmt: str = "mp3", bitrate: str = "192", browser: str = "none",
                  items: str | None = None) -> dict:
    """yt-dlp options without hooks. `items` uses yt-dlp's syntax, e.g. "1,3,5-8"."""
    opts = _base_options(browser) | {
        "outtmpl": str(Path(output_dir) / "%(playlist_index)03d - %(title)s.%(ext)s"),
        "download_archive": str(Path(output_dir) / ARCHIVE),
        "ignoreerrors": True,
        "nooverwrites": True,
    }
    if items:
        opts["playlist_items"] = items
    if fmt == "mp3":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": bitrate},
            {"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": False},
        ]
        opts["postprocessor_args"] = {"default": ["-id3v2_version", "3"]}
    elif fmt == "m4a":
        # YouTube's own AAC stream, saved as is: no FFmpeg, no re-encoding. Tags come from Mp4Tags.
        opts["format"] = "bestaudio[ext=m4a]"
    else:
        raise ValueError(f"unknown format: {fmt}")
    return opts


def tags_for(info: dict) -> dict:
    """Title, artist and album as YouTube Music reports them, falling back to the video's own fields."""
    tags = {
        "title": info.get("track") or info.get("title"),
        "artist": info.get("artist") or info.get("creator") or info.get("uploader") or info.get("channel"),
        "album": info.get("album"),
    }
    return {k: v for k, v in tags.items() if v}


class Mp4Tags(PostProcessor):
    """Writes tags to M4A files with mutagen, so M4A works without FFmpeg (Android)."""

    def run(self, info):
        from mutagen.mp4 import MP4

        keys = {"title": "\xa9nam", "artist": "\xa9ART", "album": "\xa9alb"}
        audio = MP4(info["filepath"])
        for name, value in tags_for(info).items():
            audio[keys[name]] = [value]
        audio.save()
        return [], info


class _Events(PostProcessor):
    """Runs last, after the file is in its final place: the track is done."""

    def __init__(self, emit):
        super().__init__()
        self.emit = emit

    def run(self, info):
        self.emit({"type": "track_done", "index": info.get("playlist_index"), "title": info.get("title"),
                   "path": info.get("filepath")})
        return [], info


class _Logger:
    def __init__(self, emit):
        self.emit = emit
        self.errors = 0

    def debug(self, msg):
        pass

    info = debug

    def warning(self, msg):
        self.emit({"type": "warning", "message": msg})

    def error(self, msg):
        self.errors += 1
        self.emit({"type": "track_skipped", "reason": msg.removeprefix("ERROR: ")})


def list_playlist(url: str, browser: str = "none") -> dict:
    """Titles and durations of the tracks, without downloading. Takes seconds even for long playlists."""
    opts = _base_options(browser) | {"extract_flat": "in_playlist", "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(normalize_url(url), download=False)
    entries = info.get("entries") or [info]
    return {
        "title": info.get("title"),
        "tracks": [
            {
                "index": i,
                "id": e.get("id"),
                "title": e.get("title"),
                "duration": e.get("duration"),
                "thumbnail": (e.get("thumbnails") or [{}])[-1].get("url"),
            }
            for i, e in enumerate(entries, 1)
            if e
        ],
    }


def download(url: str, output_dir: str = "downloads", fmt: str = "mp3", bitrate: str = "192",
             browser: str = "none", items: str | None = None, on_event=lambda e: None, cancel=None) -> dict:
    """Download the playlist into output_dir. Tracks already in the folder's archive are skipped.

    on_event gets dicts with "type": track_started, progress, track_done, track_skipped, warning, finished.
    cancel is an optional threading.Event: set it to stop after the current chunk.
    Returns the "finished" event: {"done", "skipped", "cancelled"}.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    done = []
    current = {"id": None}

    def emit(event):
        if event["type"] == "track_done":
            done.append(event)
        on_event(event)

    def check_cancel():
        # ponytail: only checked while bytes are downloading; a re-run where every track is
        # already archived can't be stopped until it ends. Add a match_filter check if that matters.
        if cancel is not None and cancel.is_set():
            raise DownloadCancelled()

    def progress_hook(d):
        check_cancel()
        info = d.get("info_dict") or {}
        if d.get("status") != "downloading":
            return
        if info.get("id") != current["id"]:
            current["id"] = info.get("id")
            emit({"type": "track_started", "index": info.get("playlist_index"), "title": info.get("title")})
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        emit({
            "type": "progress",
            "index": info.get("playlist_index"),
            "percent": 100 * d["downloaded_bytes"] / total if total and d.get("downloaded_bytes") else None,
            "speed": d.get("speed"),
            "eta": d.get("eta"),
        })

    logger = _Logger(emit)
    opts = build_options(output_dir, fmt, bitrate, browser, items) | {
        "logger": logger,
        "progress_hooks": [progress_hook],
    }
    cancelled = False
    with yt_dlp.YoutubeDL(opts) as ydl:
        if fmt == "m4a":
            ydl.add_post_processor(Mp4Tags(), when="post_process")
        ydl.add_post_processor(_Events(emit), when="after_move")
        try:
            ydl.download([normalize_url(url)])
        except DownloadCancelled:
            cancelled = True

    result = {"type": "finished", "done": len(done), "skipped": logger.errors, "cancelled": cancelled}
    on_event(result)
    return result
