"""If PyPI has a newer yt-dlp than requirements.txt asks for, raise the minimum everywhere and bump the app's patch
version. Prints the new tag (e.g. "v0.2.1") when files changed, nothing otherwise. Run from the repo root.

    python .github/scripts/bump_ytdlp.py               # ask PyPI
    python .github/scripts/bump_ytdlp.py --latest X --ejs Y   # pretend X is out (for testing)
"""

import argparse
import json
import re
import urllib.request
from pathlib import Path


def numbers(version):
    return tuple(int(n) for n in re.findall(r"\d+", version))


def from_pypi():
    with urllib.request.urlopen("https://pypi.org/pypi/yt-dlp/json", timeout=30) as response:
        info = json.load(response)["info"]
    # yt-dlp pins the exact yt-dlp-ejs it works with; the Android build lists it by hand, so it has to follow.
    ejs = next(re.search(r"==([\w.]+)", r).group(1) for r in info["requires_dist"]
               if r.startswith("yt-dlp-ejs==") and "default" in r)
    return info["version"], ejs


def replace(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"{path}: {old!r} not found")
    p.write_text(text.replace(old, new), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--latest")
    parser.add_argument("--ejs")
    args = parser.parse_args()

    current = re.search(r"yt-dlp\[default\]>=([\d.]+)", Path("requirements.txt").read_text()).group(1)
    latest, ejs = (args.latest, args.ejs) if args.latest else from_pypi()
    if numbers(latest) <= numbers(current):
        return

    old_ejs = re.search(r'"yt-dlp-ejs==([\w.]+)"', Path("pyproject.toml").read_text()).group(1)
    app = re.search(r'__version__ = "([\d.]+)', Path("ytmpd/__init__.py").read_text()).group(1)
    major, minor, patch = numbers(app)
    new_app = f"{major}.{minor}.{patch + 1}"

    replace("requirements.txt", f">={current}", f">={latest}")
    replace("pyproject.toml", f">={current}", f">={latest}")
    replace("pyproject.toml", f'"yt-dlp-ejs=={old_ejs}"', f'"yt-dlp-ejs=={ejs}"')
    replace("pyproject.toml", f'version = "{app}"', f'version = "{new_app}"')
    replace("ytmpd/__init__.py", f'"{app}"', f'"{new_app}"')
    for readme in ("README.md", "README.it.md"):  # the version badge
        replace(readme, f"yt--dlp-{current}", f"yt--dlp-{latest}")
        replace(readme, f'alt="yt-dlp {current}"', f'alt="yt-dlp {latest}"')
    print(f"v{new_app}")


if __name__ == "__main__":
    main()
