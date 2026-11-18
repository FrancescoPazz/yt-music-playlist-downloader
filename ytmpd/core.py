"""Download a YouTube / YouTube Music playlist as MP3 or M4A.

Nothing here prints: progress is reported as event dicts to `on_event`, so the CLI and the GUI can draw it their way.
Use only for content you are authorized to download.
"""

import io
import os
import re
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


def js_runtimes() -> dict:
    """Every runtime yt-dlp supports; on Android, the QuickJS binary the app ships as a native library."""
    runtimes = dict(JS_RUNTIMES)
    native = os.environ.get("ANDROID_NATIVE_LIBRARY_DIR")  # set by Flet's Python on Android
    if native and (Path(native) / "libqjs.so").is_file():
        runtimes["quickjs"] = {"path": str(Path(native) / "libqjs.so")}
    return runtimes


def js_runtime_names() -> list[str]:
    """The JavaScript runtimes found on this device, for the GUI's Settings."""
    names = [n for n in ("deno", "node", "qjs", "bun") if shutil.which(n)]
    return names + (["quickjs"] if "path" in js_runtimes()["quickjs"] else [])


def normalize_url(url: str) -> str:
    """Any youtube.com / music.youtube.com link with list= becomes the plain playlist link."""
    parsed = urlparse(url)
    playlist_id = parse_qs(parsed.query).get("list", [None])[0]
    if playlist_id and parsed.netloc in {"music.youtube.com", "www.youtube.com", "youtube.com", "m.youtube.com"}:
        return f"https://www.youtube.com/playlist?list={playlist_id}"
    return url


def bundled_ffmpeg() -> str | None:
    """FFmpeg from the imageio-ffmpeg wheel, used only when there is none on the PATH (the desktop app ships it)."""
    if shutil.which("ffmpeg"):
        return None
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # not installed (CLI, Android) or binary missing
        return None


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None or bundled_ffmpeg() is not None


def archive_path(output_dir: str) -> Path:
    """Where the list of downloaded videos lives by default: next to the files."""
    return Path(output_dir) / ARCHIVE


def archived_ids(archive: str | Path) -> set[str]:
    """Video ids listed in an archive file ("youtube <id>" per line)."""
    try:
        lines = Path(archive).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return set()
    return {line.split()[-1] for line in lines if line.strip()}


# Checked in order: the first match wins, so the more specific phrases come first.
_REASONS = (
    ("age", ("confirm your age", "age-restricted", "inappropriate for some users")),
    ("bot", ("not a bot",)),
    ("private", ("private video",)),
    ("members", ("members-only", "join this channel", "premium")),
    ("region", ("in your country", "geo restrict")),
    ("unavailable", ("video unavailable", "has been removed", "is not available", "account associated")),
    ("cookies", ("cookie",)),
    ("forbidden", ("http error 403",)),
    ("not_found", ("does not exist", "http error 404", "http error 400", "unsupported url", "is not a valid url")),
    ("network", ("unable to download webpage", "getaddrinfo", "timed out", "connection", "network is unreachable")),
)


def reason_kind(message: str) -> str:
    """Sorts a yt-dlp error into a few kinds the GUI can explain in plain words; "other" if none fits."""
    text = message.lower()
    return next((kind for kind, phrases in _REASONS if any(p in text for p in phrases)), "other")


def video_id_in(message: str) -> str | None:
    """yt-dlp errors start with "[youtube] <id>: ..."; returns that id."""
    match = re.search(r"\[youtube\] ([\w-]{11}):", message)
    return match.group(1) if match else None


def _base_options(browser: str, cookies: str | None = None) -> dict:
    opts = {
        "quiet": True,
        "noprogress": True,
        "js_runtimes": js_runtimes(),
    }
    if cookies:  # a cookies.txt file wins over the browser: it's the only way on Android
        opts["cookiefile"] = str(cookies)
    elif browser != "none":
        opts["cookiesfrombrowser"] = (browser,)
    return opts


def build_options(output_dir: str, fmt: str = "mp3", bitrate: str = "192", browser: str = "none",
                  items: str | None = None, *, cookies: str | None = None, temp_dir: str | None = None,
                  archive: str | None = None) -> dict:
    """yt-dlp options without hooks. `items` uses yt-dlp's syntax, e.g. "1,3,5-8".

    temp_dir: where partial files are downloaded and tagged; only the finished file is moved to output_dir.
    Android needs it: its Music folder refuses anything that isn't audio, such as `.part` files.
    archive: the archive file, by default next to the files (Android keeps it in app storage, for the same reason).
    """
    paths = {"home": str(output_dir)} | ({"temp": str(temp_dir)} if temp_dir else {})
    opts = _base_options(browser, cookies) | {
        "paths": paths,
        "outtmpl": "%(playlist_index)03d - %(title)s.%(ext)s",
        "download_archive": str(archive or archive_path(output_dir)),
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
        if ffmpeg := bundled_ffmpeg():
            opts["ffmpeg_location"] = ffmpeg  # its folder has no ffprobe; yt-dlp falls back to `ffmpeg -i`
    elif fmt == "m4a":
        # YouTube's own AAC stream, saved as is: no FFmpeg, no re-encoding. Tags come from Mp4Tags.
        opts["format"] = "bestaudio[ext=m4a]"
    else:
        raise ValueError(f"unknown format: {fmt}")
    return opts


# Words that make a bracketed group, or a " - …" / " | …" ending, pure noise in a music video's title.
_NOISE_WORDS = {"official", "music", "video", "audio", "lyric", "lyrics", "visualizer", "visualiser", "hd", "hq",
                "4k", "mv", "clip", "videoclip", "ufficiale", "full"}


def _is_noise(text: str) -> bool:
    words = re.findall(r"[^\W_]+", text.lower())
    return bool(words) and all(w in _NOISE_WORDS for w in words)


def clean_title(title: str) -> str:
    """"Song (Official Video) [4K]" → "Song". Groups with anything else in them, like "(Remix)", are kept."""
    cleaned = re.sub(r"\s*[(\[]([^)\]]*)[)\]]", lambda m: "" if _is_noise(m.group(1)) else m.group(0), title)
    ending = re.search(r"\s+[-|｜–]\s*([^-|｜–()\[\]]*)$", cleaned)  # no brackets: "(A - Official Video)" stays
    if ending and _is_noise(ending.group(1)):
        cleaned = cleaned[:ending.start()]
    return cleaned.strip() or title


def square_jpeg(data: bytes) -> bytes:
    """Centre square of a video thumbnail, as JPEG. Without Pillow the image is returned as it is."""
    try:
        from PIL import Image
    except ImportError:
        return data
    image = Image.open(io.BytesIO(data)).convert("RGB")
    width, height = image.size
    if abs(width / height - 4 / 3) < 0.02:  # hqdefault.jpg: a 16:9 frame with black bands above and below
        band = width * 9 // 16
        image = image.crop((0, (height - band) // 2, width, (height + band) // 2))
        width, height = image.size
    side = min(width, height)
    left, top = (width - side) // 2, (height - side) // 2
    out = io.BytesIO()
    image.crop((left, top, left + side, top + side)).save(out, "JPEG", quality=90)
    return out.getvalue()


def embed_cover(path: str, jpeg: bytes):
    if path.endswith(".m4a"):
        from mutagen.mp4 import MP4, MP4Cover

        audio = MP4(path)
        audio["covr"] = [MP4Cover(jpeg, imageformat=MP4Cover.FORMAT_JPEG)]
        audio.save()
    else:
        from mutagen.id3 import APIC, ID3

        tags = ID3(path)
        tags.delall("APIC")
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=jpeg))
        tags.save(v2_version=3)  # keep ID3v2.3, the version older players read


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


class Covers(PostProcessor):
    """Embeds the video thumbnail, cropped square, without FFmpeg (works on Android too). Never fails a track."""

    def run(self, info):
        thumbnails = sorted((t for t in info.get("thumbnails") or [] if ".jpg" in t.get("url", "")),
                            key=lambda t: t.get("preference") or 0, reverse=True)
        for thumbnail in thumbnails[:4]:  # maxresdefault.jpg is missing for some videos; fall back to smaller ones
            try:
                data = self._downloader.urlopen(thumbnail["url"]).read()
                embed_cover(info["filepath"], square_jpeg(data))
                break
            except Exception as e:
                error = e
        else:
            if thumbnails:
                self.report_warning(f"{info.get('id')}: cover not embedded: {error}")
        return [], info


class _Events(PostProcessor):
    """Runs last, after the file is in its final place: the track is done."""

    def __init__(self, emit):
        super().__init__()
        self.emit = emit

    def run(self, info):
        self.emit({"type": "track_done", "id": info.get("id"), "index": info.get("playlist_index"),
                   "title": info.get("title"), "path": info.get("filepath")})
        return [], info


class _Logger:
    def __init__(self, emit):
        self.emit = emit
        self.failed = []  # track_skipped events of the current pass
        self.current = {}  # info of the video being processed, set by _Current

    def debug(self, msg):
        pass

    info = debug

    def warning(self, msg):
        self.emit({"type": "warning", "message": msg})

    def error(self, msg):
        reason = msg.removeprefix("ERROR: ")
        vid = video_id_in(reason)
        if vid is None:  # e.g. "HTTP Error 403" during the download: it's about the video being processed
            vid = self.current.get("id")
        title = self.current.get("title") if vid == self.current.get("id") else None
        event = {"type": "track_skipped", "id": vid, "title": title, "reason": reason, "kind": reason_kind(reason)}
        self.failed.append(event)
        self.emit(event)


class _Current(PostProcessor):
    """Runs before each video is downloaded and remembers it, so errors without an id can be attributed."""

    def __init__(self, logger, clean=False):
        super().__init__()
        self.logger = logger
        self.clean = clean  # runs before the file name is made, so a clean title also gives a clean file name

    def run(self, info):
        if self.clean:
            info["title"] = clean_title(info.get("title") or "")
        self.logger.current = {"id": info.get("id"), "title": info.get("title")}
        return [], info


def list_playlist(url: str, browser: str = "none", cookies: str | None = None) -> dict:
    """Titles and durations of the tracks, without downloading. Takes seconds even for long playlists."""
    opts = _base_options(browser, cookies) | {"extract_flat": "in_playlist", "skip_download": True,
                                     "logger": _Logger(lambda e: None)}  # errors still raise; nothing printed
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(normalize_url(url), download=False)
    entries = info.get("entries") or [info]
    return {
        "title": info.get("title"),
        "is_playlist": "entries" in info,
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
             browser: str = "none", items: str | None = None, on_event=lambda e: None, cancel=None,
             cookies: str | None = None, temp_dir: str | None = None, archive: str | None = None,
             covers: bool = False, clean_titles: bool = False) -> dict:
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
            emit({"type": "track_started", "id": current["id"], "index": info.get("playlist_index"),
                  "title": info.get("title")})
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        emit({
            "type": "progress",
            "id": info.get("id"),
            "index": info.get("playlist_index"),
            "percent": 100 * d["downloaded_bytes"] / total if total and d.get("downloaded_bytes") else None,
            "speed": d.get("speed"),
            "eta": d.get("eta"),
        })

    logger = _Logger(emit)
    opts = build_options(output_dir, fmt, bitrate, browser, items, cookies=cookies, temp_dir=temp_dir,
                         archive=archive) | {
        "logger": logger,
        "progress_hooks": [progress_hook],
    }
    cancelled = False
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.add_post_processor(_Current(logger, clean_titles), when="pre_process")
        if fmt == "m4a":
            ydl.add_post_processor(Mp4Tags(), when="post_process")
        if covers:  # after the tags, so FFmpegMetadata (MP3) doesn't rewrite the file without the picture
            ydl.add_post_processor(Covers(), when="post_process")
        ydl.add_post_processor(_Events(emit), when="after_move")
        # YouTube sometimes answers the first request with HTTP 403 and the same request works a moment later.
        # A second pass retries only the failed tracks: the archive skips the ones already done.
        for attempt in range(2):
            logger.failed = []
            try:
                ydl.download([normalize_url(url)])
            except DownloadCancelled:
                cancelled = True
                break
            if not any(e["kind"] == "forbidden" for e in logger.failed):
                break

    result = {"type": "finished", "done": len(done), "skipped": len(logger.failed), "cancelled": cancelled}
    on_event(result)
    return result
