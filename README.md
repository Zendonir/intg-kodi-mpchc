# intg-kodi-mpchc — UC Remote Integration

[![Build & Release](https://github.com/Zendonir/intg-kodi-mpchc/actions/workflows/build.yml/badge.svg)](https://github.com/Zendonir/intg-kodi-mpchc/actions/workflows/build.yml)

UC Remote / Remote Two integration that bridges **Kodi** and **MPC-HC** into a single media-player entity via a lightweight WebSocket hub.

---

## How it works

```
UC Remote  ←→  intg-kodi-mpchc (this driver)  ←→  bridge hub  ←→  Kodi / MPC-HC
```

The [kodi-mpchc-bridge](https://github.com/Zendonir/kodi-mpchc-bridge) hub runs on the same Windows PC as Kodi/MPC-HC and exposes a unified WebSocket + REST API. This driver connects to it and presents a full-featured UC Remote integration.

---

## Features

### Media Player entity
- Play / Pause / Stop / Seek
- Next / Previous chapter
- Volume control & mute
- Shuffle & repeat modes
- D-pad navigation (Kodi UI control)
- Artwork, title (`S{s}E{e} – Title` for episodes), artist, album metadata
- Media browser with per-episode thumbnails, ▶ Now Playing indicator and Coverflow support
- Optimistic watched-mark when playlist advances to next episode

### Select entities
- **Audiospur** — switch audio track
- **Untertitel** — switch subtitle track
- **Kapitel** — jump to chapter
- **Episode** — navigate directly to any episode in the current season

### Pre-configured Remote ("Externe Fernbedienungen")
Ready-made remote with three pages and full physical button mapping:

| Page | Buttons |
|------|---------|
| Wiedergabe | Stop, Play/Pause, Skip ±, Prev/Next, Vol ±, Mute |
| Navigation | D-Pad, OK, Back, Home, Info, Menü |
| System | Zu Kodi wechseln, Zu Windows wechseln, Kodi neu starten |

### Freely assignable simple commands
Assign these to any button in the UC Remote profile editor:

| Command | Action |
|---------|--------|
| `Zu Kodi wechseln` | Switch focus to Kodi |
| `Zu Windows wechseln` | Switch to Windows desktop |
| `Kodi neu starten` | Restart Kodi |
| `Nächste Tonspur` / `Vorherige Tonspur` | Cycle audio tracks |
| `Nächster Untertitel` / `Vorheriger Untertitel` | Cycle subtitle tracks |
| `Untertitel aus` | Disable subtitles |
| `Nächstes Kapitel` / `Vorheriges Kapitel` | Jump between chapters |
| `Nächste Folge` / `Vorherige Folge` | Jump between episodes |

---

## Installation

### Requirements
- [kodi-mpchc-bridge](https://github.com/Zendonir/kodi-mpchc-bridge/releases) running on the Windows PC
- Bridge port **13590** open in the Windows firewall

### On the UC Remote
1. Download the latest `uc-intg-kodi-mpchc-*.tar.gz` from [Releases](https://github.com/Zendonir/intg-kodi-mpchc/releases).
2. In the UC Remote web-configurator go to **Integrations → Upload custom integration** and select the tar.gz.
3. Follow the setup wizard — choose **Erstinstallation** and enter the bridge host + port (default port: `13590`).

### Setup options (first-run wizard)
| Option | Description |
|--------|-------------|
| Erstinstallation | Fresh setup — enter host and port |
| Aus Backup wiederherstellen | Paste a previously saved JSON backup |
| Backup erstellen | Copy the JSON backup to save elsewhere |
| Einstellungen ändern | Change host / port of an existing device |

---

## Running with Docker

```bash
cp docker/docker-compose.yml .
# edit UC_CONFIG_HOME and bridge settings as needed
docker compose up -d
```

Or use the Makefile:

```bash
make start   # build + run
make logs    # follow logs
make down    # stop
```

---

## Development

**Requirements:** Python ≥ 3.11

```bash
pip install -r requirements.txt
pip install -r test-requirements.txt
python src/driver.py
```

**Code style:**

```bash
black src --line-length 120
isort src/.
flake8 src
pylint src
```

---

## Configuration

| Environment variable | Default | Description |
|----------------------|---------|-------------|
| `UC_CONFIG_HOME` | `.` | Directory for `config.json` storage |
| `UC_INTEGRATION_HTTP_PORT` | `9090` | Port the driver listens on |

---

## License

[Mozilla Public License 2.0](LICENSE)
