<p align="center">
  <img src="docs/logo.svg" alt="Icona: una nota musicale dentro un anello, con una freccia di download sotto" width="128">
</p>

<h1 align="center">YT Music Playlist Downloader</h1>

<p align="center">
  Uno script da riga di comando che scarica una playlist di YouTube o YouTube Music e trasforma ogni brano in MP3.<br>
  Numera i file nell'ordine della playlist, scrive i tag ID3 e può usare la sessione del browser per i video con restrizioni.
</p>

<p align="center">
  Leggi in: <a href="README.md">English</a> · Italiano
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-e0475b?style=flat&labelColor=1d1517" alt="Python 3.10 o successivo">
  <img src="https://img.shields.io/badge/yt--dlp-2026.08.19-e0475b?style=flat&labelColor=1d1517" alt="yt-dlp 2026.08.19">
  <img src="https://img.shields.io/badge/FFmpeg-richiesto-e0475b?style=flat&labelColor=1d1517" alt="FFmpeg richiesto">
  <img src="https://img.shields.io/badge/MP3-128%E2%80%93320%20kbps-e0475b?style=flat&labelColor=1d1517" alt="MP3 da 128 a 320 kbps">
  <img src="https://img.shields.io/badge/un%20file-downloader.py-e0475b?style=flat&labelColor=1d1517" alt="Un solo file: downloader.py">
</p>

## Da dove partire

| Vuoi | Vai a |
|---|---|
| **Scaricare subito una playlist** | [Installazione](#installazione), poi [Uso](#uso): due comandi e un link. |
| **Sapere cosa finisce sul disco** | [Come funziona](#come-funziona): nomi dei file, tag e brani saltati. |
| **Scaricare video con limite d'età o privati** | [Cookie del browser](#cookie-del-browser): usa la sessione in cui hai già fatto l'accesso. |
| **Qualcosa è andato storto** | [Domande](#domande-frequenti): FFmpeg, buchi nella numerazione, file `NA`. |

[Come funziona](#come-funziona) · [Installazione](#installazione) · [Uso](#uso) · [Cookie del browser](#cookie-del-browser) ·
[Sviluppo](#sviluppo) · [Domande](#domande-frequenti)

## Come funziona

Dai allo script il link di una playlist. Lui lo passa a [yt-dlp](https://github.com/yt-dlp/yt-dlp), scarica l'audio
migliore di ogni video e lo fa convertire in MP3 da FFmpeg.

| Passo | Cosa fa lo script |
|---|---|
| **1. Controllo** | Si ferma con codice di uscita 2 se `ffmpeg` non è nel PATH, prima di scaricare qualsiasi cosa. |
| **2. Link** | Un link di `music.youtube.com` o `youtube.com` con il parametro `list=` diventa `https://www.youtube.com/playlist?list=…`, quindi funziona anche il link copiato da un brano in riproduzione dentro la playlist. |
| **3. Download** | Prende il miglior flusso audio. Si presenta a YouTube prima come client web mobile (`mweb`) e poi ripiega su quello predefinito, perché YouTube sta spostando sempre più traffico sullo streaming SABR, che alcuni client gestiscono male. |
| **4. Conversione** | FFmpeg trasforma l'audio in MP3 al bitrate scelto (192 kbps se non dici altro). |
| **5. Tag** | Scrive titolo, artista e gli altri metadati forniti da YouTube come tag ID3v2.3, la versione letta da Esplora file di Windows e dai lettori più vecchi. Niente copertina. |
| **6. Salto** | Un video rimosso, privato o bloccato nel tuo paese viene saltato e il resto della playlist prosegue. |

I file finiscono in `downloads/` con la posizione nella playlist davanti al titolo:

```text
downloads/
├── 001 - Jain - Makeba (Ian Asher Remix).mp3
├── 002 - Felix Jaehn, Whitney Houston - It's Not Right But It's Okay (Official Video).mp3
├── 004 - David Guetta & Bebe Rexha - I'm Good (Blue) [Djs From Mars Remix] [VISUALIZER].mp3
└── …
```

La riga di avanzamento mostra percentuale, velocità e tempo rimanente del brano in download.

## Installazione

Servono Python 3.10 o successivo e FFmpeg.

```bash
python -m pip install -r requirements.txt
ffmpeg -version
```

Se il secondo comando non viene trovato, installa FFmpeg (su Windows `winget install Gyan.FFmpeg`) e apri un nuovo
terminale, così il PATH viene ricaricato.

YouTube cambia spesso e le versioni vecchie di yt-dlp smettono di funzionare: aggiornalo quando i download iniziano a
fallire.

```bash
python -m pip install -U yt-dlp
python -m yt_dlp --version
```

## Uso

```bash
python downloader.py "https://music.youtube.com/playlist?list=..."
```

| Opzione | Valori | Predefinito | Cosa fa |
|---|---|---|---|
| `url` | un link di playlist | | La playlist da scaricare. Mettilo tra virgolette: altrimenti la `&` di alcuni link spezza il comando. |
| `-o`, `--output` | una cartella | `downloads` | Dove vanno gli MP3. La cartella viene creata se non esiste. |
| `-b`, `--bitrate` | `128`, `192`, `256`, `320` | `192` | Bitrate degli MP3 in kbps. |
| `--browser` | `none`, `chrome`, `edge`, `firefox`, `brave`, `opera`, `vivaldi` | `none` | Browser da cui yt-dlp legge i cookie. Vedi [Cookie del browser](#cookie-del-browser). |

```bash
python downloader.py "URL" -b 320                       # qualità massima
python downloader.py "URL" -o "D:\Musica\Estate 2026"   # un'altra cartella
python downloader.py "URL" --browser firefox -b 256     # con i cookie di Firefox
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

Tutto il programma è [`downloader.py`](downloader.py), circa 170 righe con una sola dipendenza.

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows; su macOS e Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python downloader.py --help
```

<details>
<summary><b>Struttura del progetto</b></summary>

| Percorso | Contenuto |
|---|---|
| `downloader.py` | Opzioni da riga di comando, normalizzazione del link, opzioni di yt-dlp e riga di avanzamento |
| `requirements.txt` | `yt-dlp`, l'unica dipendenza |
| `docs/` | Logo di questo README |
| `downloads/` | Cartella di output predefinita, ignorata da git |

</details>

<details>
<summary><b>Dove cambiare le cose</b></summary>

| Vuoi cambiare | Guarda |
|---|---|
| Schema dei nomi dei file | `outtmpl` in `build_options()`. I campi sono quelli dell'[output template di yt-dlp](https://github.com/yt-dlp/yt-dlp#output-template). |
| Inserire la copertina | `writethumbnail` in `build_options()`, più il postprocessor `EmbedThumbnail`. |
| Quale client YouTube provare per primo | `player_client` in `extractor_args`. |
| Browser supportati | La tupla `BROWSERS` in cima al file. |

</details>

<details>
<summary><b>Codici di uscita</b></summary>

| Codice | Significato |
|---|---|
| `0` | Scaricato tutto. |
| `1` | yt-dlp ha segnalato almeno un errore (per esempio un video saltato), oppure il download si è fermato per un errore imprevisto. |
| `2` | FFmpeg non è nel PATH. |

</details>

## Domande frequenti

<details>
<summary><b>"FFmpeg non è presente nel PATH", ma l'ho installato.</b></summary>

Il terminale legge il PATH quando si apre. Chiudilo, aprine uno nuovo e prova `ffmpeg -version`. Se ancora non lo
trova, la cartella con `ffmpeg.exe` (di solito una cartella `bin`) va aggiunta al PATH a mano.

</details>

<details>
<summary><b>Mancano alcuni numeri, per esempio non c'è il 003.</b></summary>

Quel video non si è potuto scaricare: rimosso, privato, bloccato nel tuo paese o con restrizioni. Il numero è la sua
posizione nella playlist, quindi il buco resta. Se era un problema di accesso, riprova con `--browser`.

</details>

<details>
<summary><b>Un file si chiama "NA - …" invece di avere un numero.</b></summary>

Il link puntava a un singolo video, non a una playlist, quindi yt-dlp non ha una posizione da mettere davanti al
titolo. Usa il link della playlist, quello con `list=`.

</details>

<details>
<summary><b>I download falliscono con "Sign in to confirm you're not a bot" o HTTP 403.</b></summary>

Per prima cosa aggiorna yt-dlp (`python -m pip install -U yt-dlp`): dopo un cambiamento lato YouTube è la soluzione più
comune. Se continua, usa `--browser` con un browser in cui hai fatto l'accesso.

</details>

Usalo solo per contenuti che hai il diritto di scaricare, rispettando i termini di servizio di YouTube e il diritto
d'autore di ogni brano.
