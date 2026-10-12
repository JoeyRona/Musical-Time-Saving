"""Music-theory building blocks: note names, chord templates and key profiles.

Pitch classes are integers 0-11 with C = 0, C# = 1, ... B = 11.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

# Keys that are conventionally spelled with flats.
_FLAT_MAJOR_TONICS = {5, 10, 3, 8, 1}  # F, Bb, Eb, Ab, Db
_FLAT_MINOR_TONICS = {2, 7, 0, 5, 10}  # Dm, Gm, Cm, Fm, Bbm

# Krumhansl-Kessler key profiles: how strongly each scale degree is
# perceived to "belong" to a major or minor key (from listener studies).
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11]
NATURAL_MINOR_SCALE = [0, 2, 3, 5, 7, 8, 10]

# Chord qualities as intervals above the root.
CHORD_INTERVALS = {
    "maj": (0, 4, 7),
    "min": (0, 3, 7),
}


@dataclass(frozen=True)
class Key:
    tonic: int  # pitch class
    mode: str  # "major" or "minor"

    @property
    def uses_flats(self) -> bool:
        tonics = _FLAT_MAJOR_TONICS if self.mode == "major" else _FLAT_MINOR_TONICS
        return self.tonic in tonics

    def note_name(self, pitch_class: int) -> str:
        names = FLAT_NAMES if self.uses_flats else SHARP_NAMES
        return names[pitch_class % 12]

    @property
    def name(self) -> str:
        return f"{self.note_name(self.tonic)} {self.mode}"

    @property
    def scale(self) -> list[int]:
        steps = MAJOR_SCALE if self.mode == "major" else NATURAL_MINOR_SCALE
        return [(self.tonic + s) % 12 for s in steps]

    def diatonic_chords(self) -> set[tuple[int, str]]:
        """The major/minor triads that occur naturally in this key."""
        if self.mode == "major":
            qualities = ["maj", "min", "min", "maj", "maj", "min", None]  # vii° skipped
        else:
            qualities = ["min", None, "maj", "min", "min", "maj", "maj"]  # ii° skipped
        chords = {(root, q) for root, q in zip(self.scale, qualities) if q is not None}
        if self.mode == "minor":
            # Harmonic-minor V (e.g. E major in A minor) is very common.
            chords.add(((self.tonic + 7) % 12, "maj"))
        return chords


@dataclass(frozen=True)
class Chord:
    root: int  # pitch class
    quality: str  # "maj" or "min"

    @property
    def pitch_classes(self) -> list[int]:
        return [(self.root + i) % 12 for i in CHORD_INTERVALS[self.quality]]

    def name(self, key: Key | None = None) -> str:
        root = key.note_name(self.root) if key else SHARP_NAMES[self.root]
        return root + ("m" if self.quality == "min" else "")


def chord_templates() -> tuple[list[Chord], np.ndarray]:
    """All 24 major/minor triads and a unit-length 12-d template for each.

    A real string doesn't just sound its own note: it also produces overtones
    an octave, an octave + fifth, two octaves and two octaves + major third
    above. So each chord note contributes a little energy to those pitch
    classes too, otherwise a C chord (whose overtones include G, B and E)
    would look a lot like E minor. The root gets extra weight because it is
    usually the lowest and loudest note.
    """
    # (harmonic number -> semitones above the note, modulo the octave)
    harmonic_shift = {1: 0, 2: 0, 3: 7, 4: 0, 5: 4, 6: 7}
    chords: list[Chord] = []
    rows = []
    for quality in ("maj", "min"):
        for root in range(12):
            chord = Chord(root, quality)
            vec = np.zeros(12)
            for w, pc in zip((1.3, 1.0, 1.0), chord.pitch_classes):
                for k, shift in harmonic_shift.items():
                    vec[(pc + shift) % 12] += w * 0.6 ** (k - 1)
            chords.append(chord)
            rows.append(vec / np.linalg.norm(vec))
    return chords, np.array(rows)


def key_profiles() -> tuple[list[Key], np.ndarray]:
    """All 24 keys and their (rotated) Krumhansl-Kessler profiles."""
    keys: list[Key] = []
    rows = []
    for mode, profile in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
        for tonic in range(12):
            keys.append(Key(tonic, mode))
            rows.append(np.roll(profile, tonic))
    return keys, np.array(rows)
