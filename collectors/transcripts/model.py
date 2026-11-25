"""One transcript shape for Zoom, Teams and Meet, and its rendering. Pure, no I/O.

Speaker names are replaced by "Speaker 1", "Speaker 2", ... in order of first speech
before anything is stored: transcripts name real people and the platform shows roles and
counts, never names (CLAUDE.md sections 8 and 10). The rendered text is what the RAID
extractor quotes, so it is stored verbatim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Cue:
    """One stretch of speech."""

    speaker: str | None  # as the source names them; never stored
    text: str


@dataclass(frozen=True)
class Transcript:
    """One meeting's transcript from any source."""

    meeting_id: str
    title: str
    started_at: datetime
    ended_at: datetime  # when the transcript exists (meeting end, or when it was created)
    cues: tuple[Cue, ...]


def render(cues: tuple[Cue, ...] | list[Cue]) -> str:
    """``Speaker N: text`` lines, consecutive cues by one speaker joined."""
    numbers: dict[str, int] = {}
    lines: list[tuple[str, str]] = []
    for cue in cues:
        text = " ".join(cue.text.split())
        if not text:
            continue
        if cue.speaker:
            numbers.setdefault(cue.speaker, len(numbers) + 1)
            who = f"Speaker {numbers[cue.speaker]}"
        else:
            who = "Speaker"
        if lines and lines[-1][0] == who:
            lines[-1] = (who, f"{lines[-1][1]} {text}")
        else:
            lines.append((who, text))
    return "\n".join(f"{who}: {text}" for who, text in lines)


_TIMING = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?[.,]\d{3}\s+-->\s+")
_VOICE = re.compile(r"^<v\s+([^>]+)>(.*?)(?:</v>)?$", re.DOTALL)
_COLON = re.compile(r"^([^:]{1,80}):\s+(.+)$", re.DOTALL)


def parse_vtt(vtt: str) -> list[Cue]:
    """WebVTT cues with speakers.

    Microsoft Teams marks speakers with voice tags (``<v Name>text</v>``); Zoom writes
    ``Name: text``. Cue numbers, timings, ``NOTE`` blocks and the header are dropped.
    """
    cues: list[Cue] = []
    blocks = re.split(r"\n\s*\n", vtt.replace("\r\n", "\n").lstrip("﻿"))
    for block in blocks:
        lines = [ln for ln in block.strip().split("\n") if ln.strip()]
        if not lines or lines[0].startswith(("WEBVTT", "NOTE", "STYLE")):
            continue
        timing = next((i for i, ln in enumerate(lines) if _TIMING.match(ln)), None)
        if timing is None:
            continue
        body = " ".join(lines[timing + 1 :]).strip()
        if not body:
            continue
        voice = _VOICE.match(body)
        if voice:
            cues.append(Cue(voice.group(1).strip(), voice.group(2).strip()))
            continue
        named = _COLON.match(body)
        if named and not named.group(1).strip().startswith(("http", "https")):
            cues.append(Cue(named.group(1).strip(), named.group(2).strip()))
        else:
            cues.append(Cue(None, body))
    return cues
