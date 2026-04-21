# Kodi / MPC-HC Bridge Integration — Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

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
