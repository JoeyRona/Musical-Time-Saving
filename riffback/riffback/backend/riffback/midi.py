"""A small Standard MIDI File (SMF) writer.

Writing MIDI by hand is only ~80 lines: a file is a header chunk ("MThd")
followed by track chunks ("MTrk"), and each track is a list of events, each
preceded by the time since the previous event as a variable-length number.
"""

from __future__ import annotations

import struct

from .arrange import Arrangement, Note

PPQ = 480  # ticks per quarter note

TRACKS = {
    # name: (MIDI channel 0-15, General MIDI program 0-127, display name)
    "drums": (9, 0, "Drums"),
    "bass": (1, 33, "Bass"),  # Electric Bass (finger)
    "keys": (2, 4, "Keys"),  # Electric Piano 1
}


def _varlen(value: int) -> bytes:
    """Encode an int as a MIDI variable-length quantity (7 bits per byte)."""
    if value < 0:
        raise ValueError("Delta times can't be negative")
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def _meta(kind: int, data: bytes) -> bytes:
    return bytes([0xFF, kind]) + _varlen(len(data)) + data


def _chunk(kind: bytes, data: bytes) -> bytes:
    return kind + struct.pack(">I", len(data)) + data


def _track(events: list[tuple[int, int, bytes]]) -> bytes:
    """events: (absolute tick, sort order, raw event bytes). Note-offs sort
    before note-ons at the same tick so repeated notes retrigger cleanly."""
    events.sort(key=lambda e: (e[0], e[1]))
    out = bytearray()
    now = 0
    for tick, _, data in events:
        out += _varlen(tick - now) + data
        now = tick
    out += _varlen(0) + _meta(0x2F, b"")  # end of track
    return _chunk(b"MTrk", bytes(out))


def _conductor_track(tempo: float, beats_per_bar: int, title: str) -> bytes:
    usec_per_beat = int(round(60_000_000 / tempo))
    events = [
        (0, 0, _meta(0x03, title.encode("ascii", "replace"))),
        (0, 0, _meta(0x51, usec_per_beat.to_bytes(3, "big"))),
        # time signature: numerator, log2(denominator), clocks/click, 32nds/quarter
        (0, 0, _meta(0x58, bytes([beats_per_bar, 2, 24, 8]))),
    ]
    return _track(events)


def _part_track(name: str, notes: list[Note]) -> bytes:
    channel, program, display = TRACKS[name]
    events: list[tuple[int, int, bytes]] = [
        (0, 0, _meta(0x03, display.encode())),
        (0, 0, bytes([0xC0 | channel, program])),
    ]
    for n in notes:
        on = int(round(n.start * PPQ))
        off = max(on + 1, int(round((n.start + n.duration) * PPQ)))
        vel = max(1, min(127, n.velocity))
        events.append((on, 2, bytes([0x90 | channel, n.pitch, vel])))
        events.append((off, 1, bytes([0x80 | channel, n.pitch, 0])))
    return _track(events)


def to_midi(arrangement: Arrangement, parts: list[str] | None = None, title: str = "RiffBack") -> bytes:
    """Build a type-1 MIDI file containing the requested parts (default: all)."""
    parts = parts or list(TRACKS)
    unknown = set(parts) - set(TRACKS)
    if unknown:
        raise ValueError(f"Unknown part(s): {', '.join(sorted(unknown))}")

    tracks = [_conductor_track(arrangement.tempo, arrangement.beats_per_bar, title)]
    tracks += [_part_track(p, arrangement.track(p)) for p in parts]
    header = _chunk(b"MThd", struct.pack(">HHH", 1, len(tracks), PPQ))
    return header + b"".join(tracks)
