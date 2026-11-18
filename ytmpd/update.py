"""Is there a newer release on GitHub? The app asks once at startup. Standard library (plus certifi) only."""

import json
import re
import ssl
import urllib.request

REPO = "FrancescoPazz/yt-music-playlist-downloader"
ISSUES = f"https://github.com/{REPO}/issues/new"


def version_tuple(version: str) -> tuple[int, ...]:
    """"v0.2.1" and "0.2.1-dev.3" both give (0, 2, 1): the pre-release part is ignored."""
    return tuple(int(n) for n in re.findall(r"\d+", version.split("-")[0]))


def is_newer(tag: str, current: str) -> bool:
    return version_tuple(tag) > version_tuple(current)


def latest_release(timeout: float = 5) -> dict:
    """{"tag", "url"} of the latest published release (pre-releases excluded). Raises on network errors."""
    try:  # Android's Python has no system CA store; certifi ships with yt-dlp's dependencies
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    request = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                     headers={"Accept": "application/vnd.github+json",
                                              "User-Agent": "yt-music-playlist-downloader"})
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        data = json.load(response)
    return {"tag": data["tag_name"], "url": data["html_url"]}
