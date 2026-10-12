"""Turn detected chords into drum, bass and keys parts.

All positions are measured in beats from the first downbeat (bar 1, beat 1).
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from typing import Literal

from .analysis import ChordEvent
from .theory import Chord

DrumStyle = Literal["rock", "halftime", "ballad", "four-on-floor"]
BassStyle = Literal["roots", "eighths", "root-fifth", "walking"]

DRUM_STYLES: tuple[str, ...] = ("rock", "halftime", "ballad", "four-on-floor")
BASS_STYLES: tuple[str, ...] = ("roots", "eighths", "root-fifth", "walking")

# General MIDI drum map (channel 10).
KICK, SIDE_STICK, SNARE, CLOSED_HAT, OPEN_HAT, CRASH, RIDE = 36, 37, 38, 42, 46, 49, 51

BASS_LOW, BASS_HIGH = 28, 40  # E1 .. E2: the bottom octave of a 4-string bass


@dataclass
class Note:
    track: str  # "drums", "bass" or "keys"
    start: float  # beats from bar 1
    duration: float  # beats
    pitch: int  # MIDI note number
    velocity: int  # 1-127

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Arrangement:
    tempo: float
    beats_per_bar: int
    total_beats: int
    notes: list[Note]

    def track(self, name: str) -> list[Note]:
        return [n for n in self.notes if n.track == name]

    def to_dict(self) -> dict:
        return {
            "tempo": self.tempo,
            "beats_per_bar": self.beats_per_bar,
            "total_beats": self.total_beats,
            "notes": [n.to_dict() for n in self.notes],
        }


# --------------------------------------------------------------------------
# Drums
# --------------------------------------------------------------------------

# Each pattern lists (beat position within the bar, drum, velocity).
_PATTERNS: dict[str, list[tuple[float, int, int]]] = {
    "rock": [
        (0, KICK, 110),
        (2, KICK, 100),
        (2.5, KICK, 80),
        (1, SNARE, 110),
        (3, SNARE, 110),
        *[(i / 2, CLOSED_HAT, 85 if i % 2 == 0 else 65) for i in range(8)],
    ],
    "halftime": [
        (0, KICK, 110),
        (1.5, KICK, 85),
        (2, SNARE, 115),
        *[(i / 2, CLOSED_HAT, 75 if i % 2 == 0 else 55) for i in range(8)],
    ],
    "ballad": [
        (0, KICK, 95),
        (2.5, KICK, 70),
        (1, SIDE_STICK, 80),
        (3, SIDE_STICK, 80),
        *[(i, RIDE, 70) for i in range(4)],
    ],
    "four-on-floor": [
        *[(i, KICK, 110) for i in range(4)],
        (1, SNARE, 100),
        (3, SNARE, 100),
        *[(i + 0.5, OPEN_HAT, 80) for i in range(4)],
    ],
}


def _drum_fill(bar_start: float) -> list[Note]:
    """Four sixteenth-note snare hits leading into the next bar."""
    return [Note("drums", bar_start + 3 + i / 4, 0.25, SNARE, 70 + 12 * i) for i in range(4)]


def drums(total_bars: int, loop_bars: int, style: str, beats_per_bar: int = 4) -> list[Note]:
    pattern = _PATTERNS[style]
    notes: list[Note] = []
    for bar in range(total_bars):
        start = bar * beats_per_bar
        last_bar_of_loop = (bar + 1) % loop_bars == 0 and bar + 1 < total_bars
        for pos, drum, vel in pattern:
            if last_bar_of_loop and style in ("rock", "halftime") and pos >= 3:
                continue  # leave room for the fill
            notes.append(Note("drums", start + pos, 0.25, drum, vel))
        if bar % loop_bars == 0:
            notes.append(Note("drums", start, 1.0, CRASH, 100 if bar == 0 else 85))
        if last_bar_of_loop and style in ("rock", "halftime"):
            notes.extend(_drum_fill(start))
    # A final hit to end on.
    end = total_bars * beats_per_bar
    notes += [Note("drums", end, 2.0, CRASH, 110), Note("drums", end, 0.5, KICK, 110)]
    return notes


# --------------------------------------------------------------------------
# Bass and keys
# --------------------------------------------------------------------------


def _bass_pitch(pitch_class: int) -> int:
    """Lowest note of this pitch class inside the bass range."""
    p = BASS_LOW + (pitch_class - BASS_LOW) % 12
    return p if p <= BASS_HIGH else p - 12


def _chord_per_beat(chords: list[ChordEvent], loop_beats: int, beats_per_bar: int) -> list[Chord | None]:
    per_beat: list[Chord | None] = [None] * loop_beats
    for ev in chords:
        start = ev.bar * beats_per_bar + ev.beat
        for b in range(start, min(start + ev.beats, loop_beats)):
            per_beat[b] = Chord(ev.root, ev.quality)
    # Fill gaps with the previous chord (or the first one).
    first = next((c for c in per_beat if c), None)
    last = first
    for i, c in enumerate(per_beat):
        if c is None:
            per_beat[i] = last
        last = per_beat[i]
    return per_beat


def bass(chord_at: list[Chord | None], style: str, beats_per_bar: int = 4) -> list[Note]:
    notes: list[Note] = []
    n = len(chord_at)
    for beat, chord in enumerate(chord_at):
        if chord is None:
            continue
        root = _bass_pitch(chord.root)
        third = root + (4 if chord.quality == "maj" else 3)
        fifth = root + 7
        pos_in_bar = beat % beats_per_bar
        changed = beat == 0 or chord_at[beat - 1] != chord
        accent = 105 if pos_in_bar == 0 or changed else 88

        if style == "roots":
            notes.append(Note("bass", beat, 0.9, root, accent))
        elif style == "eighths":
            notes.append(Note("bass", beat, 0.45, root, accent))
            notes.append(Note("bass", beat + 0.5, 0.45, root, 80))
        elif style == "root-fifth":
            # Root on beats 1 and 3 of a bar (or on a mid-bar chord change),
            # fifth on beats 2 and 4.
            if pos_in_bar % 2 == 0 or changed:
                notes.append(Note("bass", beat, 0.95, root, accent))
            else:
                notes.append(Note("bass", beat, 0.95, fifth - 12 if fifth > BASS_HIGH + 5 else fifth, 85))
        elif style == "walking":
            nxt = chord_at[beat + 1] if beat + 1 < n else chord_at[0]
            if changed:
                pitch = root
            elif nxt is not None and nxt != chord:
                # Approach the next chord's root from a semitone below.
                pitch = _bass_pitch(nxt.root) - 1
            else:
                pitch = [root, third, fifth, third][pos_in_bar]
            notes.append(Note("bass", beat, 0.95, pitch, accent))
        else:
            raise ValueError(f"Unknown bass style: {style}")
    return notes


def keys(chords: list[ChordEvent], beats_per_bar: int = 4) -> list[Note]:
    """Sustained triads with simple voice leading: each chord uses the
    inversion closest to the previous one so the part moves smoothly."""
    notes: list[Note] = []
    prev: list[int] | None = None
    for ev in chords:
        chord = Chord(ev.root, ev.quality)
        options = []
        for inversion in range(3):
            pcs = chord.pitch_classes[inversion:] + chord.pitch_classes[:inversion]
            voicing = []
            p = 52  # start searching from E3
            for pc in pcs:
                p = p + (pc - p) % 12
                voicing.append(p)
                p += 1
            options.append(voicing)
        if prev is None:
            voicing = min(options, key=lambda v: abs(v[0] - 55))
        else:
            voicing = min(options, key=lambda v: sum(abs(a - b) for a, b in zip(v, prev)))
        prev = voicing
        start = ev.bar * beats_per_bar + ev.beat
        notes += [Note("keys", start, ev.beats - 0.05, p, 70) for p in voicing]
    return notes


# --------------------------------------------------------------------------
# Putting it together
# --------------------------------------------------------------------------


def arrange(
    chords: list[ChordEvent],
    bars: int,
    tempo: float,
    drum_style: str = "rock",
    bass_style: str = "roots",
    repeats: int = 2,
    beats_per_bar: int = 4,
    humanize: bool = True,
    seed: int = 7,
) -> Arrangement:
    if drum_style not in DRUM_STYLES:
        raise ValueError(f"Unknown drum style: {drum_style}")
    if bass_style not in BASS_STYLES:
        raise ValueError(f"Unknown bass style: {bass_style}")
    if not chords:
        raise ValueError("No chords to arrange.")

    loop_beats = bars * beats_per_bar
    chord_at = _chord_per_beat(chords, loop_beats, beats_per_bar) * repeats
    looped = [
        ChordEvent(ev.bar + r * bars, ev.beat, ev.beats, ev.root, ev.quality, ev.name)
        for r in range(repeats)
        for ev in chords
    ]

    notes = drums(bars * repeats, bars, drum_style, beats_per_bar)
    notes += bass(chord_at, bass_style, beats_per_bar)
    notes += keys(looped, beats_per_bar)

    if humanize:
        # Small, repeatable velocity variation so it sounds less robotic.
        rng = random.Random(seed)
        for n in notes:
            n.velocity = max(1, min(127, n.velocity + rng.randint(-6, 6)))

    notes.sort(key=lambda n: (n.start, n.track, n.pitch))
    return Arrangement(tempo=tempo, beats_per_bar=beats_per_bar, total_beats=loop_beats * repeats, notes=notes)
