<p align="center">
  <img src="docs/logo.svg" alt="App icon: a music note inside a ring, with a download arrow underneath" width="128">
</p>

<h1 align="center">YT Music Playlist Downloader</h1>

<p align="center">
  A command-line script that downloads a YouTube or YouTube Music playlist and turns every track into an MP3.<br>
  It numbers the files in playlist order, writes the ID3 tags and can use your browser's session for restricted videos.
</p>

<p align="center">
  Read in: English · <a href="README.it.md">Italiano</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-e0475b?style=flat&labelColor=1d1517" alt="Python 3.10 or later">
  <img src="https://img.shields.io/badge/yt--dlp-2026.08.19-e0475b?style=flat&labelColor=1d1517" alt="yt-dlp 2026.08.19">
  <img src="https://img.shields.io/badge/FFmpeg-required-e0475b?style=flat&labelColor=1d1517" alt="FFmpeg required">
  <img src="https://img.shields.io/badge/MP3-128%E2%80%93320%20kbps-e0475b?style=flat&labelColor=1d1517" alt="MP3 from 128 to 320 kbps">
  <img src="https://img.shields.io/badge/one%20file-downloader.py-e0475b?style=flat&labelColor=1d1517" alt="One file: downloader.py">
</p>

## Start here

| You want to | Go to |
|---|---|
| **Download a playlist now** | [Install](#install), then [Usage](#usage): two commands and a link. |
| **Know what ends up on disk** | [How it works](#how-it-works): file names, tags and skipped tracks. |
| **Download age-restricted or private videos** | [Browser cookies](#browser-cookies): use the session you are already signed in with. |
| **Something went wrong** | [Questions](#questions-people-ask): FFmpeg, gaps in the numbering, `NA` files. |

[How it works](#how-it-works) · [Install](#install) · [Usage](#usage) · [Browser cookies](#browser-cookies) ·
[Development](#development) · [Questions](#questions-people-ask)

## How it works

You give the script the link of a playlist. It hands it to [yt-dlp](https://github.com/yt-dlp/yt-dlp), downloads the
best available audio of each video and has FFmpeg convert it to MP3.

| Step | What the script does |
|---|---|
| **1. Check** | Stops with exit code 2 if `ffmpeg` is not on the PATH, before downloading anything. |
| **2. Link** | A link from `music.youtube.com` or `youtube.com` with a `list=` parameter becomes `https://www.youtube.com/playlist?list=…`, so a link copied from a song playing inside the playlist works too. |
| **3. Download** | Takes the best audio stream. It asks YouTube as the mobile web client first (`mweb`) and falls back to the default one, because YouTube is moving more traffic to SABR streaming, which some clients handle badly. |
| **4. Convert** | FFmpeg turns the audio into MP3 at the bitrate you chose (192 kbps unless you say otherwise). |
| **5. Tag** | Writes the title, artist and the other metadata YouTube provides as ID3v2.3 tags, the version Windows Explorer and older players read. No cover art. |
| **6. Skip** | A video that is deleted, private or blocked in your country is skipped and the rest of the playlist goes on. |

The files land in `downloads/` with the playlist position in front of the title:

```text
downloads/
├── 001 - Jain - Makeba (Ian Asher Remix).mp3
├── 002 - Felix Jaehn, Whitney Houston - It's Not Right But It's Okay (Official Video).mp3
├── 004 - David Guetta & Bebe Rexha - I'm Good (Blue) [Djs From Mars Remix] [VISUALIZER].mp3
└── …
```

The progress line shows percentage, speed and time left for the track being downloaded. The messages are in Italian.

## Install

You need Python 3.10 or later and FFmpeg.

```bash
python -m pip install -r requirements.txt
ffmpeg -version
```

If the second command isn't found, install FFmpeg (on Windows `winget install Gyan.FFmpeg`) and open a new terminal so
the PATH is reloaded.

YouTube changes often and old versions of yt-dlp stop working, so update it whenever downloads start failing:

```bash
python -m pip install -U yt-dlp
python -m yt_dlp --version
```

## Usage

```bash
python downloader.py "https://music.youtube.com/playlist?list=..."
```

| Option | Values | Default | What it does |
|---|---|---|---|
| `url` | a playlist link | | The playlist to download. Put it in quotes: the `&` in some links breaks the command otherwise. |
| `-o`, `--output` | a folder | `downloads` | Where the MP3s go. The folder is created if it doesn't exist. |
| `-b`, `--bitrate` | `128`, `192`, `256`, `320` | `192` | MP3 bitrate in kbps. |
| `--browser` | `none`, `chrome`, `edge`, `firefox`, `brave`, `opera`, `vivaldi` | `none` | Browser whose cookies yt-dlp reads. See [Browser cookies](#browser-cookies). |

```bash
python downloader.py "URL" -b 320                       # best quality
python downloader.py "URL" -o "D:\Music\Summer 2026"    # another folder
python downloader.py "URL" --browser firefox -b 256     # with Firefox cookies
```

## Browser cookies

Some videos ask you to sign in: age-restricted ones, private or unlisted playlists, Premium-only uploads. With
`--browser`, yt-dlp reads the cookies of the YouTube session open in that browser and downloads as you.

| Case | What to do |
|---|---|
| **Public playlist** | Nothing: the default `--browser none` is enough. |
| **Age-restricted videos** | Sign in to YouTube in the browser, then add `--browser firefox` (or the one you use). |
| **Your private playlist** | Same as above, with the account that owns the playlist. |
| **Chrome or Edge on Windows** | Close the browser before running the script, because it locks its cookies while open. Recent versions also encrypt them in a way yt-dlp often can't read: if you get a cookie error, sign in with Firefox and use `--browser firefox`. |

The script only reuses access you already have in the browser. It doesn't get around DRM or access checks, and videos
you can't play in the browser won't download either.

YouTube rotates its cookies often, so a session read from the browser can expire in the middle of a long playlist. If
that happens regularly, the [yt-dlp wiki](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies)
explains how to export cookies from a private window that stay valid longer.

## Development

The whole program is [`downloader.py`](downloader.py), about 170 lines with a single dependency.

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows; on macOS and Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python downloader.py --help
```

<details>
<summary><b>Project layout</b></summary>

| Path | Contents |
|---|---|
| `downloader.py` | Command-line options, link normalization, yt-dlp options and the progress line |
| `requirements.txt` | `yt-dlp`, the only dependency |
| `docs/` | Logo for this README |
| `downloads/` | Default output folder, ignored by git |

</details>

<details>
<summary><b>Where to change things</b></summary>

| You want to change | Look at |
|---|---|
| File name pattern | `outtmpl` in `build_options()`. The fields are [yt-dlp's output template](https://github.com/yt-dlp/yt-dlp#output-template) ones. |
| Embedding the cover art | `writethumbnail` in `build_options()`, plus the `EmbedThumbnail` postprocessor. |
| Which YouTube client to ask first | `player_client` in `extractor_args`. |
| Supported browsers | The `BROWSERS` tuple at the top of the file. |

</details>

<details>
<summary><b>Exit codes</b></summary>

| Code | Meaning |
|---|---|
| `0` | Everything downloaded. |
| `1` | yt-dlp reported at least one error (for example a skipped video), or the download stopped on an unexpected error. |
| `2` | FFmpeg is not on the PATH. |

</details>

## Questions people ask

<details>
<summary><b>"FFmpeg non è presente nel PATH", but I installed it.</b></summary>

The terminal reads the PATH when it opens. Close it, open a new one and try `ffmpeg -version`. If it still isn't found,
the folder with `ffmpeg.exe` (usually a `bin` folder) has to be added to the PATH by hand.

</details>

<details>
<summary><b>Some numbers are missing, for example there is no 003.</b></summary>

That video couldn't be downloaded: deleted, private, blocked in your country or restricted. The number is its position
in the playlist, so the gap stays. If it was a sign-in problem, try again with `--browser`.

</details>

<details>
<summary><b>A file is called "NA - …" instead of having a number.</b></summary>

The link pointed to a single video, not a playlist, so yt-dlp has no position to put in front of the title. Use the
playlist link, the one with `list=`.

</details>

<details>
<summary><b>Downloads fail with "Sign in to confirm you're not a bot" or HTTP 403.</b></summary>

Update yt-dlp first (`python -m pip install -U yt-dlp`): it's the most common fix after a change on YouTube's side. If it
keeps happening, use `--browser` with a browser where you are signed in.

</details>

Use it only for content you are allowed to download, following YouTube's terms of service and the copyright of each
track.
