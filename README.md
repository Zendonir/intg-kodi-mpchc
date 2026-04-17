# intg-kodi-mpchc — UC Remote Integration

[![Build & Release](https://github.com/Zendonir/intg-kodi-mpchc/actions/workflows/build.yml/badge.svg)](https://github.com/Zendonir/intg-kodi-mpchc/actions/workflows/build.yml)

A [UC Remote / Remote Two](https://www.unfoldedcircle.com/) integration that bridges **Kodi** and **MPC-HC** into a single media-player entity via a lightweight WebSocket hub.

## How it works

```
UC Remote ←→ intg-kodi-mpchc (this driver) ←→ bridge hub ←→ Kodi / MPC-HC
```

The bridge hub runs on the same PC as Kodi/MPC-HC and exposes a unified WebSocket + REST API. This driver connects to it and presents a full-featured UC Remote media-player entity.

## Features

- Play / Pause / Stop / Seek
- Next / Previous chapter
- Volume control & mute
- Audio track & subtitle selection
- Artwork, title, artist, album metadata
- Shuffle & repeat modes
- D-pad navigation
- Auto-reconnect on bridge disconnect

## Installation on UC Remote

1. Download the latest `uc-intg-kodi-mpchc-*.tar.gz` from [Releases](https://github.com/Zendonir/intg-kodi-mpchc/releases).
2. In the Remote Two web-configurator go to **Integrations → Upload custom integration** and select the tar.gz.
3. Follow the setup wizard and enter your bridge host + port (default: `13580`).

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

## Configuration

| Environment variable       | Default | Description                        |
|----------------------------|---------|------------------------------------|
| `UC_CONFIG_HOME`           | `.`     | Directory for `config.json` storage|
| `UC_INTEGRATION_HTTP_PORT` | `9090`  | Port the driver listens on         |

## License

[Mozilla Public License 2.0](LICENSE)
