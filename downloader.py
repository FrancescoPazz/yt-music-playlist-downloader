#!/usr/bin/env python3
"""
YouTube / YouTube Music Playlist -> MP3 downloader.

Use only for content you are authorized to download.
Requires FFmpeg on PATH.

Examples:
  python downloader.py "https://music.youtube.com/playlist?list=..."
  python downloader.py "URL" --browser chrome
  python downloader.py "URL" --browser firefox -b 320
"""

import argparse
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import yt_dlp


BROWSERS = ("none", "chrome", "edge", "firefox", "brave", "opera", "vivaldi")


def progress_hook(d):
    if d.get("status") == "downloading":
        percent = d.get("_percent_str", "").strip()
        speed = d.get("_speed_str", "").strip()
        eta = d.get("_eta_str", "").strip()
        print(
            f"\r{percent:>8} | {speed:>12} | ETA {eta:>6}",
            end="",
            flush=True,
        )
    elif d.get("status") == "finished":
        print("\nConversione in MP3...")


def normalize_url(url: str) -> str:
    """YouTube Music playlists are redirected by yt-dlp to YouTube anyway."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    playlist_id = qs.get("list", [None])[0]

    if playlist_id and parsed.netloc in {"music.youtube.com", "www.youtube.com", "youtube.com"}:
        return f"https://www.youtube.com/playlist?list={playlist_id}"

    return url


def build_options(output_dir: str, bitrate: str, browser: str):
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(Path(output_dir) / "%(playlist_index)03d - %(title)s.%(ext)s"),
        "noplaylist": False,
        "ignoreerrors": True,
        "nooverwrites": True,
        "continuedl": True,
        "quiet": True,
        "progress_hooks": [progress_hook],

        # YouTube has been moving more traffic to SABR. Prefer mweb and
        # keep default as a fallback.
        "extractor_args": {
            "youtube": {
                "player_client": ["mweb", "default"],
            }
        },

        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": bitrate,
        }],
        "postprocessor_args": ["-id3v2_version", "3"],
        "addmetadata": True,
        "writethumbnail": False,
    }

    if browser != "none":
        opts["cookiesfrombrowser"] = (browser,)

    return opts


def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        print(
            "ERRORE: FFmpeg non è presente nel PATH.\n"
            "Installa FFmpeg e riapri il terminale.",
            file=sys.stderr,
        )
        return False
    return True


def download_playlist(url: str, output_dir: str, bitrate: str, browser: str):
    if not check_ffmpeg():
        return 2

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    url = normalize_url(url)

    print(f"Playlist: {url}")
    print(f"Output:   {Path(output_dir).resolve()}")
    print(f"MP3:      {bitrate} kbps")
    print(f"Browser:  {browser}")
    print()

    if browser != "none":
        print(
            "Nota: yt-dlp leggerà i cookie della sessione del browser. "
            "Per i video con limite d'età devi essere normalmente autenticato "
            "su YouTube nel browser scelto."
        )
        print()

    opts = build_options(output_dir, bitrate, browser)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return_code = ydl.download([url])
    except Exception as exc:
        print(f"\nErrore: {exc}", file=sys.stderr)
        return 1

    print("\nDownload completato.")
    return int(return_code or 0)


def main():
    parser = argparse.ArgumentParser(
        description="Scarica una playlist YouTube/YouTube Music e converte l'audio in MP3."
    )
    parser.add_argument("url", help="URL della playlist")
    parser.add_argument(
        "-o", "--output",
        default="downloads",
        help="Cartella di output (default: downloads)",
    )
    parser.add_argument(
        "-b", "--bitrate",
        choices=["128", "192", "256", "320"],
        default="192",
        help="Bitrate MP3 (default: 192)",
    )
    parser.add_argument(
        "--browser",
        choices=BROWSERS,
        default="none",
        help=(
            "Browser da cui leggere i cookie. "
            "Usa 'none' per non usare cookie. Default: none."
        ),
    )

    args = parser.parse_args()
    raise SystemExit(
        download_playlist(
            args.url,
            args.output,
            args.bitrate,
            args.browser,
        )
    )


if __name__ == "__main__":
    main()
