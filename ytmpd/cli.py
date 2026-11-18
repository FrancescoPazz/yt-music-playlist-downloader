"""Command line: prints the core's events in Italian."""

import argparse
import sys
from pathlib import Path

from yt_dlp.utils import format_bytes, formatSeconds

from . import core


def print_event(e):
    kind = e["type"]
    if kind == "track_started":
        number = f"{e['index']:03d}" if e["index"] else "---"
        print(f"\n[{number}] {e['title']}")
    elif kind == "progress":
        percent = f"{e['percent']:5.1f}%" if e["percent"] is not None else "    ?"
        speed = f"{format_bytes(e['speed'])}/s" if e["speed"] else ""
        eta = formatSeconds(e["eta"]) if e["eta"] is not None else ""
        print(f"\r{percent:>8} | {speed:>12} | ETA {eta:>6}", end="", flush=True)
    elif kind == "track_done":
        print(f"\n  Salvato: {Path(e['path']).name}")
    elif kind == "track_skipped":
        print(f"\n  Saltato: {e['reason']}", file=sys.stderr)
    elif kind == "warning":
        print(f"\n  Attenzione: {e['message']}", file=sys.stderr)
    elif kind == "finished":
        status = "Download annullato" if e["cancelled"] else "Download completato"
        print(f"\n{status}: {e['done']} scaricati, {e['skipped']} saltati.")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Scarica una playlist YouTube/YouTube Music in MP3 o M4A."
    )
    parser.add_argument("url", help="URL della playlist")
    parser.add_argument("-o", "--output", default="downloads", help="Cartella di output (default: downloads)")
    parser.add_argument("-f", "--format", choices=core.FORMATS, default="mp3",
                        help="mp3 (richiede FFmpeg) o m4a (audio originale, senza FFmpeg). Default: mp3")
    parser.add_argument("-b", "--bitrate", choices=core.BITRATES, default="192",
                        help="Bitrate MP3 (default: 192). Ignorato con m4a.")
    parser.add_argument("--browser", choices=core.BROWSERS, default="none",
                        help="Browser da cui leggere i cookie. Usa 'none' per non usare cookie. Default: none.")
    parser.add_argument("--items", help="Solo questi brani, per posizione: es. 1,3,5-8")
    parser.add_argument("--list", action="store_true", help="Elenca i brani della playlist senza scaricarli")
    parser.add_argument("--covers", action="store_true", help="Inserisce nel file la miniatura del video come copertina")
    parser.add_argument("--clean-titles", action="store_true",
                        help="Toglie \"(Official Video)\", \"[VISUALIZER]\" e simili da titolo e nome del file")
    args = parser.parse_args(argv)

    if args.list:
        playlist = core.list_playlist(args.url, args.browser)
        print(playlist["title"] or "")
        for t in playlist["tracks"]:
            duration = f"{int(t['duration']) // 60}:{int(t['duration']) % 60:02d}" if t["duration"] else "?"
            print(f"{t['index']:03d}  {duration:>8}  {t['title']}")
        return 0

    if args.format == "mp3" and not core.ffmpeg_available():
        print("ERRORE: FFmpeg non è presente nel PATH.\n"
              "Installa FFmpeg e riapri il terminale, oppure usa -f m4a.", file=sys.stderr)
        return 2

    print(f"Playlist: {core.normalize_url(args.url)}")
    print(f"Output:   {Path(args.output).resolve()}")
    print(f"Formato:  {args.format}" + (f" {args.bitrate} kbps" if args.format == "mp3" else ""))
    print(f"Browser:  {args.browser}")
    if args.browser != "none":
        print("\nNota: yt-dlp leggerà i cookie della sessione del browser. Per i video con limite d'età "
              "devi essere normalmente autenticato su YouTube nel browser scelto.")

    try:
        result = core.download(args.url, args.output, args.format, args.bitrate, args.browser, args.items,
                               on_event=print_event, covers=args.covers, clean_titles=args.clean_titles)
    except Exception as exc:
        print(f"\nErrore: {exc}", file=sys.stderr)
        return 1
    return 1 if result["skipped"] else 0
