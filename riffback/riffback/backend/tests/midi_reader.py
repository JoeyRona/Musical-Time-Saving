"""Minimal MIDI file parser used by the tests to check what we wrote."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


@dataclass
class Track:
    name: str = ""
    tempo_usec: int | None = None
    time_signature: tuple[int, int] | None = None
    program: int | None = None
    # (tick, kind, channel, pitch, velocity), kind is "on" or "off"
    notes: list[tuple[int, str, int, int, int]] = field(default_factory=list)


@dataclass
class MidiFile:
    format: int
    ppq: int
    tracks: list[Track]


def _read_varlen(data: bytes, i: int) -> tuple[int, int]:
    value = 0
    while True:
        b = data[i]
        i += 1
        value = (value << 7) | (b & 0x7F)
        if not b & 0x80:
            return value, i


def parse(data: bytes) -> MidiFile:
    assert data[:4] == b"MThd", "missing MThd header"
    length, fmt, ntracks, ppq = struct.unpack(">IHHH", data[4:14])
    i = 8 + length
    tracks = []
    for _ in range(ntracks):
        assert data[i : i + 4] == b"MTrk", "missing MTrk chunk"
        (size,) = struct.unpack(">I", data[i + 4 : i + 8])
        body = data[i + 8 : i + 8 + size]
        i += 8 + size
        track = Track()
        j, tick = 0, 0
        while j < len(body):
            delta, j = _read_varlen(body, j)
            tick += delta
            status = body[j]
            if status == 0xFF:
                kind = body[j + 1]
                ln, k = _read_varlen(body, j + 2)
                payload = body[k : k + ln]
                j = k + ln
                if kind == 0x03:
                    track.name = payload.decode("ascii", "replace")
                elif kind == 0x51:
                    track.tempo_usec = int.from_bytes(payload, "big")
                elif kind == 0x58:
                    track.time_signature = (payload[0], 2 ** payload[1])
                elif kind == 0x2F:
                    break
            elif status & 0xF0 == 0xC0:
                track.program = body[j + 1]
                j += 2
            elif status & 0xF0 in (0x80, 0x90):
                ch, pitch, vel = status & 0x0F, body[j + 1], body[j + 2]
                kind = "on" if status & 0xF0 == 0x90 and vel > 0 else "off"
                track.notes.append((tick, kind, ch, pitch, vel))
                j += 3
            else:
                raise AssertionError(f"unexpected status byte {status:#x}")
        tracks.append(track)
    return MidiFile(fmt, ppq, tracks)
