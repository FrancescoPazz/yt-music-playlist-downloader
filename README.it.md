<p align="center">
  <img src="docs/logo.svg" alt="Icona: una nota musicale dentro un anello, con una freccia di download sotto" width="128">
</p>

<h1 align="center">YT Music Playlist Downloader</h1>

<p align="center">
  Uno script da riga di comando che scarica una playlist di YouTube o YouTube Music e salva ogni brano in MP3 o M4A.<br>
  Numera i file nell'ordine della playlist, scrive i tag, ricorda cosa ha già scaricato e può usare la sessione del browser per i video con restrizioni.
</p>

<p align="center">
  Leggi in: <a href="README.md">English</a> · Italiano
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-e0475b?style=flat&labelColor=1d1517" alt="Python 3.10 o successivo">
  <img src="https://img.shields.io/badge/yt--dlp-2026.10.26-e0475b?style=flat&labelColor=1d1517" alt="yt-dlp 2026.10.26">
  <img src="https://img.shields.io/badge/MP3-128%E2%80%93320%20kbps-e0475b?style=flat&labelColor=1d1517" alt="MP3 da 128 a 320 kbps">
  <img src="https://img.shields.io/badge/M4A-senza%20FFmpeg-e0475b?style=flat&labelColor=1d1517" alt="M4A senza FFmpeg">
  <img src="https://img.shields.io/badge/GUI-in%20roadmap-e0475b?style=flat&labelColor=1d1517" alt="GUI nella roadmap">
  <img src="https://img.shields.io/badge/license-MIT-e0475b?style=flat&labelColor=1d1517" alt="Licenza MIT">
</p>

## Da dove partire

| Vuoi | Vai a |
|---|---|
| **Scaricare subito una playlist** | [Installazione](#installazione), poi [Uso](#uso): due comandi e un link. |
| **Sapere cosa finisce sul disco** | [Come funziona](#come-funziona): nomi dei file, tag, brani saltati e nuove esecuzioni. |
| **Scaricare video con limite d'età o privati** | [Cookie del browser](#cookie-del-browser): usa la sessione in cui hai già fatto l'accesso. |
| **Usarlo dal tuo codice Python** | [Sviluppo](#sviluppo): il pacchetto `ytmpd` e i suoi eventi. |
| **Qualcosa è andato storto** | [Domande](#domande-frequenti): FFmpeg, buchi nella numerazione, file `NA`, HTTP 403. |

[Come funziona](#come-funziona) · [Installazione](#installazione) · [Uso](#uso) · [Cookie del browser](#cookie-del-browser) ·
[Sviluppo](#sviluppo) · [Roadmap](ROADMAP.md) · [Domande](#domande-frequenti)

## Come funziona

Dai allo script il link di una playlist. Lui lo passa a [yt-dlp](https://github.com/yt-dlp/yt-dlp), scarica l'audio
migliore di ogni video e lo salva in MP3 o M4A.

| Passo | Cosa fa lo script |
|---|---|
| **1. Controllo** | Per l'MP3, si ferma con codice di uscita 2 se `ffmpeg` non è nel PATH, prima di scaricare qualsiasi cosa. |
| **2. Link** | Un link di `music.youtube.com` o `youtube.com` con il parametro `list=` diventa `https://www.youtube.com/playlist?list=…`, quindi funziona anche il link copiato da un brano in riproduzione dentro la playlist. |
| **3. Download** | Prende il miglior flusso audio. YouTube nasconde i flussi dietro una verifica in JavaScript: yt-dlp la risolve con Deno, Node.js, QuickJS o Bun, quello che trova installato. |
| **4. Conversione** | **MP3**: FFmpeg converte l'audio al bitrate scelto (192 kbps se non dici altro). **M4A**: il flusso AAC originale di YouTube viene salvato così com'è, senza conversione e senza perdere qualità. |
| **5. Tag** | Titolo e artista (e album, quando YouTube Music lo conosce). Gli MP3 ricevono tag ID3v2.3, la versione letta da Esplora file di Windows e dai lettori più vecchi. Niente copertina. |
| **6. Salto** | Un video rimosso, privato o bloccato nel tuo paese viene saltato e il resto della playlist prosegue. |
| **7. Memoria** | Ogni brano scaricato viene annotato in `.ytmpd-archive.txt` nella cartella di output. Rilanciando la stessa playlist scarica solo i brani aggiunti nel frattempo. |

I file finiscono in `downloads/` con la posizione nella playlist davanti al titolo:

```text
downloads/
├── .ytmpd-archive.txt
├── 001 - Jain - Makeba (Ian Asher Remix).mp3
├── 002 - Felix Jaehn, Whitney Houston - It's Not Right But It's Okay (Official Video).mp3
├── 004 - David Guetta & Bebe Rexha - I'm Good (Blue) [Djs From Mars Remix] [VISUALIZER].mp3
└── …
```

Per ogni brano il terminale mostra il titolo, poi percentuale, velocità e tempo rimanente, poi il nome del file salvato.

## Installazione

Serve Python 3.10 o successivo. FFmpeg serve solo per l'MP3, e un runtime JavaScript (Deno o Node.js) è fortemente
consigliato: senza, YouTube offre meno formati e alcuni download falliscono.

```bash
python -m pip install -r requirements.txt
ffmpeg -version
node --version     # oppure: deno --version
```

| Manca | Installalo con (Windows) |
|---|---|
| FFmpeg | `winget install Gyan.FFmpeg`, poi apri un nuovo terminale così il PATH viene ricaricato |
| Deno | `winget install DenoLand.Deno` |
| Node.js | `winget install OpenJS.NodeJS.LTS` |

YouTube cambia spesso e le versioni vecchie di yt-dlp smettono di funzionare: aggiornalo quando i download iniziano a
fallire.

```bash
python -m pip install -U "yt-dlp[default]"
python -m yt_dlp --version
```

## Uso

```bash
python downloader.py "https://music.youtube.com/playlist?list=..."
```

| Opzione | Valori | Predefinito | Cosa fa |
|---|---|---|---|
| `url` | un link di playlist | | La playlist da scaricare. Mettilo tra virgolette: altrimenti la `&` di alcuni link spezza il comando. |
| `-o`, `--output` | una cartella | `downloads` | Dove vanno i file. La cartella viene creata se non esiste. |
| `-f`, `--format` | `mp3`, `m4a` | `mp3` | MP3 (serve FFmpeg) o M4A (l'audio AAC originale, senza FFmpeg). |
| `-b`, `--bitrate` | `128`, `192`, `256`, `320` | `192` | Bitrate degli MP3 in kbps. Ignorato con l'M4A. |
| `--browser` | `none`, `chrome`, `edge`, `firefox`, `brave`, `opera`, `vivaldi` | `none` | Browser da cui yt-dlp legge i cookie. Vedi [Cookie del browser](#cookie-del-browser). |
| `--items` | posizioni, es. `1,3,5-8` | tutti | Scarica solo questi brani. |
| `--list` | | | Elenca i brani con posizione e durata, senza scaricarli. |

```bash
python downloader.py "URL" --list                        # guarda cosa contiene
python downloader.py "URL" --items 1-10 -b 320           # primi dieci brani, MP3 alla qualità massima
python downloader.py "URL" -f m4a -o "D:\Musica\Estate"  # audio originale, un'altra cartella
python downloader.py "URL" --browser firefox             # con i cookie di Firefox
```

## Cookie del browser

Alcuni video chiedono l'accesso: quelli con limite d'età, le playlist private o non in elenco, i contenuti solo
Premium. Con `--browser`, yt-dlp legge i cookie della sessione YouTube aperta in quel browser e scarica a nome tuo.

| Caso | Cosa fare |
|---|---|
| **Playlist pubblica** | Niente: basta il predefinito `--browser none`. |
| **Video con limite d'età** | Accedi a YouTube nel browser, poi aggiungi `--browser firefox` (o quello che usi). |
| **Una tua playlist privata** | Come sopra, con l'account proprietario della playlist. |
| **Chrome o Edge su Windows** | Chiudi il browser prima di lanciare lo script, perché mentre è aperto blocca i cookie. Le versioni recenti li cifrano anche in un modo che yt-dlp spesso non riesce a leggere: se ricevi un errore sui cookie, accedi con Firefox e usa `--browser firefox`. |

Lo script riusa solo l'accesso che hai già nel browser. Non aggira DRM né controlli di accesso, e i video che non puoi
riprodurre nel browser non si scaricano nemmeno qui.

YouTube ruota spesso i cookie, quindi una sessione letta dal browser può scadere a metà di una playlist lunga. Se
succede di frequente, il [wiki di yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies)
spiega come esportare da una finestra in incognito dei cookie che durano di più.

## Sviluppo

Il codice è nel pacchetto `ytmpd`: `core` fa il lavoro e non stampa niente, `cli` è la riga di comando costruita sopra.
L'interfaccia grafica prevista nella [roadmap](ROADMAP.md) userà `core` allo stesso modo.

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows; su macOS e Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest            # test, non serve la rete
```

```python
import threading
from ytmpd import core

cancel = threading.Event()        # cancel.set() da un altro thread ferma il download
result = core.download("https://music.youtube.com/playlist?list=...", "downloads", fmt="m4a",
                       on_event=print, cancel=cancel)
# result == {"type": "finished", "done": 12, "skipped": 1, "cancelled": False}
```

| `type` dell'evento | Altre chiavi | Quando |
|---|---|---|
| `track_started` | `index`, `title` | Arrivano i primi byte di un brano |
| `progress` | `index`, `percent`, `speed` (byte/s), `eta` (s) | Più volte al secondo durante il download; ognuna può essere `None` |
| `track_done` | `index`, `title`, `path` | Il file è al suo posto, con i tag |
| `track_skipped` | `reason` | yt-dlp ha rinunciato a un video |
| `warning` | `message` | yt-dlp ha segnalato qualcosa, per esempio l'assenza di un runtime JavaScript |
| `finished` | `done`, `skipped`, `cancelled` | Sempre per ultimo; è anche il valore restituito |

`core.list_playlist(url)` restituisce in pochi secondi il titolo della playlist e i suoi brani (`index`, `id`, `title`,
`duration`, `thumbnail`), senza scaricare niente.

<details>
<summary><b>Struttura del progetto</b></summary>

| Percorso | Contenuto |
|---|---|
| `ytmpd/core.py` | Normalizzazione del link, opzioni di yt-dlp, elenco della playlist, download con eventi e annullamento, tag M4A |
| `ytmpd/cli.py` | Opzioni da riga di comando e messaggi in italiano |
| `downloader.py` | Wrapper di due righe, così `python downloader.py` continua a funzionare |
| `tests/test_core.py` | Test su link, opzioni e tag (`python -m unittest`) |
| `requirements.txt` | `yt-dlp[default]`, che porta con sé `yt-dlp-ejs` (il risolutore della verifica JavaScript) e `mutagen` (tag M4A) |
| `ROADMAP.md` | Piano per l'app con interfaccia grafica, desktop e Android |
| `DEVLOG.md` | Cosa ha scoperto ogni fase, a partire dalla prova su Android |
| `spike/android/` | App Flet usa e getta per provare `ytmpd.core` su Android |
| `docs/` | Logo di questo README |
| `downloads/` | Cartella di output predefinita, ignorata da git |

</details>

<details>
<summary><b>Dove cambiare le cose</b></summary>

| Vuoi cambiare | Guarda |
|---|---|
| Schema dei nomi dei file | `outtmpl` in `core.build_options()`. I campi sono quelli dell'[output template di yt-dlp](https://github.com/yt-dlp/yt-dlp#output-template). |
| Quali tag vengono scritti | `core.tags_for()` per l'M4A; il postprocessor `FFmpegMetadata` per l'MP3. |
| Inserire la copertina | `writethumbnail` in `core.build_options()`, più il postprocessor `EmbedThumbnail`. |
| Browser e formati supportati | `BROWSERS` e `FORMATS` in cima a `core.py`. |

</details>

<details>
<summary><b>Codici di uscita</b></summary>

| Codice | Significato |
|---|---|
| `0` | Scaricato tutto (o era già nell'archivio). |
| `1` | Almeno un brano è stato saltato, oppure il download si è fermato per un errore imprevisto. |
| `2` | Scelto l'MP3 e FFmpeg non è nel PATH. |

</details>

## Domande frequenti

<details>
<summary><b>"FFmpeg non è presente nel PATH", ma l'ho installato.</b></summary>

Il terminale legge il PATH quando si apre. Chiudilo, aprine uno nuovo e prova `ffmpeg -version`. Se ancora non lo
trova, la cartella con `ffmpeg.exe` (di solito una cartella `bin`) va aggiunta al PATH a mano. Oppure fai a meno di
FFmpeg con `-f m4a`.

</details>

<details>
<summary><b>Mancano alcuni numeri, per esempio non c'è il 003.</b></summary>

Quel video non si è potuto scaricare: rimosso, privato, bloccato nel tuo paese o con restrizioni. Il numero è la sua
posizione nella playlist, quindi il buco resta. Se era un problema di accesso, riprova con `--browser`: i brani già
scaricati vengono saltati.

</details>

<details>
<summary><b>Un file si chiama "NA - …" invece di avere un numero.</b></summary>

Il link puntava a un singolo video, non a una playlist, quindi yt-dlp non ha una posizione da mettere davanti al
titolo. Usa il link della playlist, quello con `list=`.

</details>

<details>
<summary><b>L'ho rilanciato e non ha scaricato niente.</b></summary>

Era già tutto in `.ytmpd-archive.txt`. Per riscaricare un brano, cancella la sua riga da quel file (o cancella il file
per ricominciare da capo). Le cartelle riempite con le versioni precedenti all'archivio vengono riscaricate una volta.

</details>

<details>
<summary><b>I download falliscono con "Sign in to confirm you're not a bot" o HTTP 403.</b></summary>

Un 403 isolato può essere un momento storto di YouTube: rilancia il comando, i brani già fatti vengono saltati. Se
continua, aggiorna yt-dlp (`python -m pip install -U "yt-dlp[default]"`), controlla che Deno o Node.js siano
installati, e poi prova `--browser` con un browser in cui hai fatto l'accesso.

</details>

Usalo solo per contenuti che hai il diritto di scaricare, rispettando i termini di servizio di YouTube e il diritto
d'autore di ogni brano.

Rilasciato con [licenza MIT](LICENSE).
