# Kodi / MPC-HC Bridge Integration — Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

---

## v0.1.2 - 2026-04-23
### Fixed
- Select entities (Audiospur, Untertitel, Kapitel, Folge) no longer show a
  persistent red error symbol after Kodi was offline — STATE is now explicitly
  set to UNAVAILABLE when no options are available and back to ON when data
  arrives, clearing any prior error indicator
- Kiosk commands (Zu Kodi wechseln / Zu Windows wechseln / Kodi neu starten)
  now correctly call the bridge REST endpoints /api/kiosk/* instead of the
  generic /api/command route where they were silently ignored
- ON / OFF / TOGGLE media player commands mapped to valid bridge equivalents
- Episode navigation (Nächste/Vorherige Folge) uses the bridge's
  next_episode / prev_episode commands directly

---

## v0.1.1 - 2026-04-22
### Fixed
- Bridge WebSocket connection is now kept alive during UC Remote standby —
  the "connection lost" symbol no longer appears after briefly switching to Windows
- Removed unreachable code in setup flow (pylint W0101)

---

## v0.1.0 - 2026-04-21
### Initial release
- Media player entity with full play/pause/seek/volume/track control
- WebSocket bridge client with auto-reconnect
- Episode titles displayed as `S{s}E{e} – Title`
- Media browser (UC Remote ≥ 2.9.1) with ▶ Now Playing indicator,
  per-episode thumbnails and Coverflow support
- Optimistic watched-mark when the playlist advances to the next episode
- Pre-configured remote ("Externe Fernbedienungen") with three pages:
  Wiedergabe, Navigation, System
- Simple commands freely assignable to any button:
  Zu Windows wechseln · Zu Kodi wechseln · Kodi neu starten
  Nächste/Vorherige Tonspur · Nächster/Vorheriger Untertitel · Untertitel aus
  Nächstes/Vorheriges Kapitel · Nächste/Vorherige Folge
- Audio track, subtitle and chapter select entities (Audiospur, Untertitel, Kapitel)
- Episode select entity for direct season navigation
- Sensor entities for bridge state fields
- Multi-step setup flow with fresh-install, backup/restore and settings options
- Docker support
- GitHub Actions CI producing aarch64 tar.gz release
