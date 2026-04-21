# Kodi / MPC-HC Bridge Integration — Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

---

## v0.10.0 - 2026-04-21
### Added
- **Pre-configured remote** ("Externe Fernbedienungen") — a ready-made
  `Remote` entity with three pages and full physical button mapping:
  - **Wiedergabe**: Stop, Play/Pause, Skip ±, Prev/Next, Vol ±, Mute
  - **Navigation**: D-Pad, OK, Back, Home, Info, Menü
  - **System**: Zu Kodi wechseln, Zu Windows wechseln, Kodi neu starten

---

## v0.9.2 - 2026-04-21
### Added
- Specific navigation commands as simple commands on the media player —
  appear by name in the UC Remote command picker and can be assigned to
  any button freely:
  - Nächste / Vorherige Tonspur
  - Nächster / Vorheriger Untertitel · Untertitel aus
  - Nächstes / Vorheriges Kapitel
  - Nächste / Vorherige Folge

---

## v0.9.1 - 2026-04-21
### Changed
- Entity names now bilingual (de/en): Audiospur, Untertitel, Kapitel.
- Simple commands renamed to German:
  `Zu Windows wechseln`, `Zu Kodi wechseln`, `Kodi neu starten`.

---

## v0.9.0 - 2026-04-20
### Changed
- **Episode list order restored**: Media browser now shows episodes in their
  natural order (S01E01 first). The ▶ Now Playing subtitle still marks the
  active episode.
- **Color buttons removed**: `COLOR_BUTTONS` feature dropped. The three
  system-switch actions are now exposed as freely-assignable simple commands
  instead — assign them to any button in the UC Remote profile editor:
  - `GOTO_WINDOWS` → switch PC to desktop
  - `GOTO_KODI`    → switch to Kodi
  - `RESTART_KODI` → restart Kodi
  - (PC restart command removed)

---

## v0.8.1 - 2026-04-20
### Fixed
- **Build CI**: Added `workflow_dispatch` trigger to `build.yml` so the
  aarch64 tar.gz release can be re-triggered manually via GitHub Actions UI
  without needing to push a new tag. Supports optional `tag` input to
  build and publish any existing tag.

---

## v0.8.0 - 2026-04-20
### Fixed
- **Setup flow loop**: Step-2 form fields (`bridge_host`, `backup_json`,
  `_backup_done`) are now checked *before* the `action` dropdown so the remote
  can never accidentally re-route a completed form back to the action menu.
- **Intermediate setup page removed**: Cleared `setup_data_schema.settings` in
  `driver.json` so the UC Remote skips its built-in pre-step and shows the
  4-option action menu as the very first page.

---

## v0.7.0 - 2026-04-20
### Added
- **Browse highlight**: Episode list is now rotated so the currently playing
  episode is always first — the UC Remote's default focus lands on it automatically.
- **Thumbnails for all episodes**: `artwork_url` used as fallback thumbnail for
  every episode in the browser, not just the active one.
- **New commands** — system/player-switch actions on color buttons:
  - 🟢 `function_green` → Wechsel zu Kodi (`switch_to_kodi`)
  - 🔵 `function_blue`  → Wechsel zu Windows (`switch_to_desktop`)
  - 🟡 `function_yellow`→ Kodi Neustart (`restart_kodi`)
  - 🔴 `function_red`   → PC neustarten (`restart_pc`)
- **Springe (relative seek)**: `channel_up` skips +30 s forward,
  `channel_down` skips -10 s backward. Amount configurable via `seconds` param.
- **Multi-step setup flow** with 4-option action menu on first page:
  1. Erstinstallation
  2. Aus Backup wiederherstellen (paste JSON)
  3. Backup erstellen (shows JSON to copy — only if installed)
  4. Einstellungen ändern (only if installed)
  Backup format changed from base64 code to readable JSON.

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
