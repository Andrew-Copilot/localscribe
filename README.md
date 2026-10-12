# Local Scribe

## Free and open-source AI-based automated audio transcription, captioning, and easy transcript editing software for researchers. 

**Retain full data custody on your own computer: no transferring to any third parties for transcription.**

<p align="center"><img src="app/static/icon/icon-256.png" width="128" height="128" alt="Local Scribe logo"></p>

<p align="center">
  <a href="https://github.com/jeremyriel/localscribe/releases/latest/download/LocalScribe-1.01.2-Windows-x86_64.exe"><strong>⬇ Download for Windows</strong></a>
  &nbsp;·&nbsp;
  <a href="https://github.com/jeremyriel/localscribe/releases/latest/download/LocalScribe-1.01.2-macOS-arm64.dmg"><strong>⬇ Download for macOS</strong></a>
  &nbsp;·&nbsp;
  <a href="https://github.com/jeremyriel/localscribe/releases/latest/download/LocalScribe-1.01.2-Linux-x86_64.AppImage"><strong>⬇ Download for Linux</strong></a>
</p>
<p align="center">
  <a href="https://github.com/jeremyriel/localscribe/releases/latest">All releases</a>
  &middot; see <a href="#installable-desktop-apps">Installing</a> below for first-run permission steps
</p>

An app by the [UIC TRAILblazer Lab](https://www.trailblazerlab.org); Jeremy Riel, PhD.

**Current version: 1.01.2** — see [Versioning](#versioning) below.

Given the emerging capabilities of open-source language models, The UIC TRAILblazer Lab presents a
free, open-source, and AI-based automated transcription app that can transcribe audio and
video file sound into workable transcription files. Also included is a transcript editor to work on transcripts after they are generated in-app. Designed for
researchers, by researchers, who are concerned about data security and protection of our research subjects' privacy in the age of AI. You don't need to send data to the cloud for transcription anymore. 

Speed up transcript generation, keep your data fully secure and in your custody, and keep humans as the validators of data. 

This app is designed for protected human-subjects data: transcription and editing
run locally, and data is not automatically sent to an external service. You can
deliberately export a review package or backup and are responsible for choosing
an approved transfer destination. All of the AI runs directly on your own computer. You can also edit and clean up transcript
files directly in the app with the virtual editor, with several
quality-of-life features like being able to quickly replay segments,
visualizing words the AI system has low confidence in categorizing, and
having timestamps clearly marked. It is intended to do the hard work of
getting a first draft done and increasing the speed by which humans validate
and de-identify transcripts for research. Review Mode queues uncertain,
possibly-artifactual, unassigned, flagged, and recently changed segments;
its progress travels with project exports. Timestamped comments and questions
travel with an optional, explicitly exported offline review package; Local
Scribe does not synchronize reviewer copies in real time. See the
[Review Mode guide](docs/review-mode.md) and
[offline handoff guide](docs/offline-handoff.md).

Local Scribe transcribes audio and video with OpenAI's Whisper models entirely
on your own computer, then gives you a browser workbench for correcting the
transcript against the audio. There is no cloud transcription service, account,
telemetry, or third-party asset in the interface; any review package or backup
is created only when you explicitly request it.

In this version, this app is for English-only texts. It may handle multilingual transcription and accents well via the Whisper AI models used, but additional language outputs are not yet available. Multiple-language testing has not yet been conducted.

> **Disclaimer.** Local Scribe is provided **"AS IS", without warranty of any
> kind**, express or implied. The authors and the UIC TRAILblazer Lab are
> **not responsible or liable** for any data loss, data breach, or other harm
> arising from installing, configuring, or using this software, including but
> not limited to mishandling of recordings, transcripts, or other data by the
> user, the operating environment, or third-party components it depends on.
> **You are solely responsible for how you use this application** — including
> compliance with your IRB protocol, institutional data-security policy, and
> applicable law, and for securing the computer it runs on. See
> [LICENSE](LICENSE) for the full legal terms.

## Starting the app

| Platform | Command |
|---|---|
| Windows | double-click **`run.bat`** |
| macOS | double-click **`run.command`** |
| Linux | **`./run.sh`** |

The first run creates a private Python environment in `.venv` and installs
dependencies (about 250 MB, a few minutes). Later runs skip that and start in
seconds. A browser opens automatically at <http://127.0.0.1:43707>.

Running the launcher again shuts down any existing instance first, so only one
copy is ever running.

### Installable desktop apps

Pre-built installers - a `.dmg` for macOS, an `.exe` installer for Windows,
an `.AppImage` for Linux - are published on the
[**Releases page**](https://github.com/jeremyriel/localscribe/releases/latest)
(links at the top of this README) so most people never need to touch a
terminal or `git clone` anything. The installed app opens in its own window
(not a browser tab), and stores your projects, models, and settings in your
normal per-user data directory rather than inside the app itself, so they
survive an update or reinstall.

These installers are **not currently signed** - the same Gatekeeper/
SmartScreen prompt described below still applies the first time you open
one, since that requires an ongoing, paid, identity-verified code-signing
setup (an Apple Developer ID + notarization on macOS, a Windows code-signing
certificate or Microsoft Trusted Signing on Windows) that hasn't been set
up yet. Linux needs no signing at all.

Prefer to build one yourself instead of downloading a prebuilt binary?
`packaging/` has the same scripts CI uses to produce each release asset:

```
packaging/macos/build.sh              # -> dist/macos/*.dmg
packaging/windows/build.ps1           # -> dist/windows/*.exe (needs Inno Setup)
packaging/linux/build-appimage.sh     # -> dist/linux/*.AppImage
```

`.github/workflows/build-installers.yml` builds and smoke-tests all three
on every push, and attaches them to a GitHub Release when one is published.

### Giving permissions for the launcher to run

The first time you run one of these scripts, your operating system may block
it as an unrecognised program, since it isn't signed by a registered
developer. This only needs to be done once per machine.

- **macOS:** Double-clicking `run.command`, or opening the installed **Local
  Scribe.app**, may show *"cannot be opened because it is from an
  unidentified developer."* Right-click (or Control-click) it and choose
  **Open**, then confirm **Open** in the dialog that appears — after that,
  double-clicking works normally. If Local Scribe was downloaded as a ZIP
  rather than with `git clone`, also run `chmod +x run.command run.sh` once
  in Terminal first, so the scripts are marked executable.

  **If Local Scribe.app opened once but now won't open at all** (no error,
  it just doesn't launch): this is macOS's Gatekeeper "App Translocation"
  running the unsigned app from a temporary, randomized location on its very
  first launch. Local Scribe's own one-time setup is unaffected by later
  translocated launches as of 1.01.2, but if you're on an older build, the
  fix is to remove the quarantine flag so macOS stops translocating it:
  ```
  xattr -dr com.apple.quarantine "/Applications/Local Scribe.app"
  ```
  then delete `~/Library/Application Support/Local Scribe/.venv` if it
  exists, and reopen the app.
- **Windows:** Double-clicking `run.bat` may trigger a **"Windows protected
  your PC"** SmartScreen warning. Click **More info**, then **Run anyway**.
  Antivirus software may also flag the first run, since it downloads and
  installs Python packages; this is expected and safe to allow.
- **Linux:** `run.sh` needs execute permission the first time:
  `chmod +x run.sh`, then run it with `./run.sh`.

### Requirements

- **Python 3.10 to 3.13.** Python 3.14 is not yet usable because CTranslate2,
  the runtime that executes the Whisper model, has no 3.14 build. The launcher
  finds a supported version automatically if you have one installed.
- No `ffmpeg` installation is needed; media handling is built in.
- A network connection is needed **once**, to install packages and download a
  model. After that the app runs fully offline.

### Windows, macOS and Linux hardware acceleration

Local Scribe runs on Windows, macOS and Linux, and automatically uses
whichever GPU acceleration your machine actually has — nothing to configure
by hand.

- **Windows and Linux (PC):** Transcription runs through CTranslate2, which
  uses an NVIDIA GPU via CUDA when one is present and its support libraries
  are installed, and falls back to CPU otherwise. AI Settings shows exactly
  what was detected and has a one-click **Install GPU support** button when
  the CUDA libraries are missing.
- **macOS (Apple Silicon):** On M-series Macs, Local Scribe takes advantage
  of Apple's **MLX** framework to run the Whisper model directly on the
  GPU, through the Mac's **unified memory architecture** — the same memory
  pool the CPU uses, so nothing has to be copied back and forth between
  separate CPU and GPU memory and there is no fixed VRAM ceiling to plan
  around. This gives Apple Silicon Macs genuine GPU-accelerated
  transcription with no discrete graphics card required, typically several
  times faster than CPU-only transcription. AI Settings offers a matching
  set of "(Apple GPU)" models when MLX is available, and recommends one
  sized to your Mac's memory. Intel Macs, and Apple Silicon Macs where MLX
  isn't installed, fall back to CPU automatically.

Either way, AI Settings recommends a model and device for your specific
hardware and explains its reasoning; you can always override it, including
forcing CPU-only if you ever want to.

## First use: Things you want to do

1. Open **AI Settings** and download a model. `large-v3-turbo` (1.6 GB) is the
   recommended default; the page recommends one based on your hardware and
   explains why.
2. Turn on **Offline lock** in AI Settings → Privacy. All outbound network
   access is then blocked inside the process, enforced at the socket level.
3. Back on **Projects**, create a project, add recordings, and press
   **Transcribe**.
4. Open a transcribed file to review it: play the audio, click the time ribbon
   or any word to hear it again, and correct the text. Edits save
   automatically.
5. Set the number of **Speakers** at the top, give each a name, a short tag and
   a colour, then tag each speaking turn by clicking its tag or pressing
   <kbd>1</kbd>–<kbd>9</kbd>. A speaker's name is printed once per turn, so a
   pause in the middle of someone talking breaks the paragraph without
   repeating their name.
6. Use **Find** (or <kbd>Ctrl</kbd>+<kbd>F</kbd>) to fix a recurring error
   across the whole transcript. Red underlines mark words that are not in the
   dictionary, blue ones mark probable transcription slips; right-click either
   for suggestions or to accept the word.
7. When the human pass is done, press **Re-timestamp and rewrite captions**,
   then download the outputs.

## What you get per recording

Written into `projects/<project>/documents/<id>/outputs/`:

| File | Purpose |
|---|---|
| `transcript.txt` | Clean prose for reading and coding |
| `transcript.md` | Markdown with metadata front matter |
| `transcript.docx` | Word document with a metadata table |
| `transcript.vtt` | WebVTT captions for video software |
| `transcript.srt` | SubRip captions |
| `transcript.json` | Full word-level data for analysis |

## Reusable vocabulary and study presets

On a project's page, create a profile from a term list or import UTF-8 `.txt`
and `.csv` files, then assign it to that project. Profiles are stored locally
with application settings and can be reused across projects. CSV files may use
a `term`, `terms`, `word`, or `words` column. A profile can target initial-prompt
context or hotwords and can optionally set language, task, beam size, best-of,
or multilingual/VAD options; a settings-only study preset is also supported.
Terms are combined with the corresponding
existing AI setting rather than silently replacing it; the existing project
glossary fallback remains intact.

Project archives and transcription provenance record the profile identity and
applied settings, but not the profile's vocabulary terms by default. The
separate local profile library is not bundled into a project export. Transcript
content and existing project metadata retain their normal export behavior.
Download **Uncertain-term report (CSV)** from the project page to review each
word whose model confidence is below the editor's low-confidence threshold.

## Supported input formats

**Audio** wav, mp3, m4a, aac, flac, ogg, opus, wma, aiff, amr, ac3, mka, caf, au
**Video** mp4, mov, m4v, mkv, avi, webm, wmv, flv, mpg, mpeg, mts, m2ts, ts,
3gp, 3g2, ogv, asf, vob, divx, f4v, rm, rmvb

Audio is extracted from video automatically. Files are validated by inspecting
their actual contents, not their extension, so a mislabelled file still works.
Original files are never modified.

## Where things live on your computer

```
projects/            your projects: media, transcripts, exports
models/              downloaded Whisper weights
logs/                rotating application log and the pidfile
settings.json        your settings
vocabulary_profiles.json   local reusable vocabulary and preset library
.venv/               the private Python environment
```

A project is plain files, so you can inspect it, copy it to an encrypted
drive, or recover a transcript with a text editor. **Export project** writes a
single versioned `.lsproj` archive with per-file SHA-256 checksums; **Import
project** verifies those checksums before restoring. You can export with or
without source media. Transient caches and logs are excluded. Older archives
remain importable, but their contents cannot be checksum-verified; Local Scribe
warns when one is imported. Transcript-only imports identify recordings whose
source media is missing, while keeping their transcripts available. See the
[`.lsproj` interchange format specification](docs/lsproj-format.md) for the
manifest, provenance, integrity, and migration contract.

### Privacy Center

Open **Privacy Center** in the top navigation to review Offline Lock, the
explicitly configured local Box Sync backup folder, local storage locations,
the last network-affecting action, and a bounded activity history for network
and recovery actions. AI Settings also offers local-only health checks for free
storage, data-folder access, selected model files, and the supported Python
runtime. Model downloads show their estimated transfer size and a recommended
free-space reserve before starting. These checks inspect local state only; they
make no outbound requests and send no data off the computer. Diagnostics are
generated as an on-screen preview and are not saved unless you inspect the
preview and choose **Save diagnostics JSON**.
The preview contains only reviewed runtime and settings status; it excludes
media, transcript content, tokens, and user paths.

## Options

```
From a terminal (using the Windows .bat file for example):
run.bat --no-browser        start without opening a browser
run.bat --port 43711        use a different port
run.bat --reinstall         force dependency reinstallation, use if something doesn't seem to be installed right or isn't working correctly.
```

The port can also be set with the `LOCALSCRIBE_PORT` environment variable.

## Troubleshooting common errors

**"Port 43707 is in use by ... which is not Local Scribe."**
Something else holds the port. Local Scribe deliberately refuses to move to
another port, so that it can never collide with another local service. Stop
that process, or start with `--port 43711`.

**Transcription is slower than expected.**
Check the status pill in the top bar. If it says CPU while you have an NVIDIA
GPU, open AI Settings — the hardware panel explains why the GPU is unavailable.
The usual causes are a missing CUDA support library (there is an install
button) or an NVIDIA driver older than 527.

**Windows: transcription fails with a missing `.dll` (for example `cublas64_12.dll`, `cudnn_ops64_9.dll` or `msvcp140.dll`).**
On an NVIDIA PC, the GPU needs two CUDA libraries, cuBLAS 12 and cuDNN 9,
which a fresh Windows install does not include. Local Scribe now checks for
them before choosing the GPU, and switches to CPU automatically if one is still
missing once transcription starts. To use the GPU, click **Install GPU
support** in AI Settings, then restart Local Scribe. If the missing file is
`msvcp140.dll` or another `vcruntime`/`msvcp` file, install the
[Microsoft Visual C++ Redistributable (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe)
and restart. The installer bundles these files, so this should only affect
source installs. Startup problems are logged to
`%LOCALAPPDATA%\Local Scribe\logs\bootstrap.log` and `localscribe.log`.

**The audio will not play in the editor.**
Formats such as `.mkv`, `.avi` and `.wmv` cannot be played by a browser, so a
small `.m4a` companion is generated during transcription. If it is missing,
re-transcribe the file, or check that "Keep browser preview audio" is on in AI
Settings.

**The transcript repeats a phrase over and over.**
Turn off "Condition on previous text" in AI Settings → Quality gates, or raise
the repetition penalty slightly, then re-transcribe.

## Tests you can run on the software

```
.venv/Scripts/python.exe -m tests.test_realign      # re-timestamping
.venv/Scripts/python.exe -m tests.test_exporters     # captions and exports
.venv/Scripts/python.exe -m tests.test_assets        # front-end asset guards
.venv/Scripts/python.exe -m tests.test_sensitivity   # project declarations and future backup policy
.venv/Scripts/python.exe -m tests.test_project_archives # archive integrity and legacy compatibility
.venv/Scripts/python.exe -m tests.test_handoff        # offline review packages and conflict handling
.venv/Scripts/python.exe -m tests.test_recovery       # local snapshots and recovery safeguards
.venv/Scripts/python.exe -m tests.test_privacy_center # sanitized diagnostics and activity history
.venv/Scripts/python.exe -m tests.test_health         # local health and model disk estimates
.venv/Scripts/python.exe -m tests.test_box_sync       # local Box Sync copy safeguards
.venv/Scripts/python.exe -m tests.test_speakers       # roster and speaking turns
.venv/Scripts/python.exe -m tests.test_proofread     # spelling and artefacts
.venv/Scripts/python.exe -m tests.test_vocabulary    # reusable profiles and presets
.venv/Scripts/python.exe -m tests.test_winlibs       # Windows DLL discovery
.venv/Scripts/python.exe -m tests.test_engine_fallback  # GPU-to-CPU fallback
```

On macOS and Linux use `.venv/bin/python` instead.

Projects have a user-declared source-media sensitivity, defaulting to
**Unknown — treat as PHI**. This controls future backup safeguards, not whether
data is PHI, and provides no compliance advice. See the
[Box Sync decision and local guardrails](docs/box-sync-decision.md).

Recovery snapshots use the verified `.lsproj` archive format and are stored
locally under `projects/.snapshots/`, outside each project folder. You can
include or omit source media when creating a snapshot. Deleting projects or
recordings offers the option to snapshot first; replacing a project during
restore creates a safety snapshot. Snapshots remain on the same computer and
are not protection from drive loss, so copy important snapshots to a separate
approved location. The app keeps a bounded local history of recovery actions.

Manual end-to-end testing of the recovery UI has not yet been performed; it is
deferred for the project owner to do later. The automated recovery tests do not
verify desktop UI behavior or an installed Box Sync client.

Optional Box Sync backup copies an archive into a folder you explicitly
configure in AI Settings and confirm on each project backup. Local Scribe does
not select a folder automatically, authenticate with Box, or verify that Box
Sync is running. Offline Lock blocks the copy. See the
[Box Sync decision and backup notes](docs/box-sync-decision.md) for policy and
limitations.

## Versioning

Local Scribe uses its own simple `MAJOR.MINOR[.BUILD]` scheme, not semantic
versioning tied to commit counts:

- **1.00** — the original release.
- **1.01** — added Apple Silicon GPU support via MLX, and the Mac/PC
  hardware-acceleration architecture described above.
- **1.01.1, 1.01.2, ...** — small fixes and tweaks on top of 1.01. A build
  number appears only once there's something to append it to; a release
  with no build suffix (like 1.01) is the first of that minor version.

The running version is in `VERSION` at the repository root, and shown on
the **About** page and in the app's window title/console banner.

## Licensing

Local Scribe is released under the **MIT licence**, copyright © 2026 Jeremy
Riel, UIC TRAILblazer Lab. See [LICENSE](LICENSE). You may use, modify and
redistribute it freely, including commercially, provided the copyright notice
and licence text are retained.

The software is provided **"AS IS", without warranty of any kind**. The
authors and copyright holders are not liable for any claim, damages, or other
liability — including data loss or a data-security breach — arising from the
software or its use. By using Local Scribe you accept full responsibility for
your own actions with it: how you configure it, what data you put into it,
and how you secure the machine it runs on.

If you use Local Scribe in published research, a citation of the software and
the UIC TRAILblazer Lab is appreciated but not required.

### Components

Whisper (OpenAI), faster-whisper, CTranslate2, python-docx, Silero VAD,
FastAPI, Starlette, uvicorn and Jinja2 are MIT or BSD licensed. PyAV is BSD
licensed and links FFmpeg, which is LGPL/GPL depending on build. The bundled
spelling dictionary is derived from SCOWL (BSD-style; its notice ships at
`app/data/dictionary/SCOWL-LICENSE.txt`). Model weights are redistributed by
their publishers under their own terms. Full detail is in
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
