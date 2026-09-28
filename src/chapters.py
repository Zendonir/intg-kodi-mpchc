"""
Chapter helpers shared by the media player and the chapter select entity.

The bridge publishes ``chapters`` as ``[{pos, name, time_ms}, …]`` plus
``current_chapter`` (0-based index). An empty list is sent as a single
sentinel entry with ``pos == -1``.

Jumping to a chapter: when the chapter's start time is known the bridge seeks
to it. Chapters reported by Kodi without an MKV parse carry ``time_ms == 0``
for every entry — those are reached by stepping with next/prev chapter.
"""

from __future__ import annotations

import re
from typing import Any

from bridge_client import BridgeClient

# Generic chapter names that add nothing to the number ("Chapter 3", "Kapitel 03", "3").
_GENERIC_NAME_RE = re.compile(
    r"^\s*(?:chapter|kapitel|chapitre|capitolo|cap[ií]tulo|ch\.?)?\s*0*\d+\s*$",
    re.IGNORECASE,
)


def real_items(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Drop the bridge's ``pos == -1`` "nothing available" sentinel entry."""
    return [item for item in items or [] if item.get("pos", 0) != -1]


def chapters_of(state: dict[str, Any]) -> list[dict[str, Any]]:
    return real_items(state.get("chapters"))


def chapter_name(chapter: dict[str, Any]) -> str:
    """Return the chapter's own name, or ``""`` when it is only a number."""
    name = (chapter.get("name") or "").strip()
    return "" if not name or name == "—" or _GENERIC_NAME_RE.match(name) else name


def chapter_label(chapter: dict[str, Any], idx: int) -> str:
    """Display label: ``3. Name`` or ``Kapitel 3``."""
    name = chapter_name(chapter)
    return f"{idx + 1}. {name}" if name else f"Kapitel {idx + 1}"


def has_timestamps(chapters: list[dict[str, Any]]) -> bool:
    """True when the chapter start times are known (not all zero)."""
    return any(ch.get("time_ms", 0) > 0 for ch in chapters[1:])


def format_time(ms: int) -> str:
    """``1:02:03`` / ``2:03`` for a chapter start time."""
    total = int(ms // 1000)
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def now_playing_text(state: dict[str, Any]) -> str:
    """``Kapitel 3/12 · Name`` for the current chapter, ``""`` without chapters."""
    chapters = chapters_of(state)
    current = state.get("current_chapter", 0)
    if len(chapters) < 2 or not 0 <= current < len(chapters):
        return ""
    text = f"Kapitel {current + 1}/{len(chapters)}"
    name = chapter_name(chapters[current])
    return f"{text} · {name}" if name else text


async def goto_chapter(client: BridgeClient, state: dict[str, Any], target: int) -> bool:
    """Jump to chapter index *target* of the currently playing file."""
    chapters = chapters_of(state)
    if not 0 <= target < len(chapters):
        return False
    if target == 0 or has_timestamps(chapters):
        return await client.send_command("seek", chapters[target].get("time_ms", 0) / 1000.0)
    # Unknown start times: step chapter by chapter from the current one.
    delta = target - state.get("current_chapter", 0)
    command = "next_chapter" if delta > 0 else "prev_chapter"
    ok = True
    for _ in range(abs(delta)):
        ok = await client.send_command(command) and ok
    return ok
