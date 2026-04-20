# Kodi / MPC-HC Bridge Integration — Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

---

## v0.6.0 - 2026-04-20
### Added
- Episode titles displayed as `S{s}E{e} – Title` everywhere (media player
  attribute, media browser, episode select). Kodi metadata is always the
  primary source; MKV filenames are never shown.
- Media browser highlights the currently playing episode with a ▶ Now Playing
  subtitle so the active item is immediately visible.
- `thumbnail` support in every `BrowseMediaItem`: per-episode image from
  bridge, with `artwork_url` as fallback for the active episode. Enables
  Coverflow / visual navigation in UC Remote.
- Season container in media browser now also carries the current artwork.
- When the Kodi playlist advances to the next episode, the completed episode
  is optimistically marked as watched locally (playcount = 1) immediately,
  before the next Kodi state push arrives.

### Fixed
- Black formatting in `setup_flow.py` (two blank lines before top-level
  functions following section comments).

---

## v0.1.0 - 2026-04-17
### Initial release
- Media player entity with full play/pause/seek/volume/track control
- WebSocket bridge client with auto-reconnect
- Setup wizard for bridge host/port configuration
- Docker support
- GitHub Actions CI producing aarch64 binary release
