"""Synthesised guitar riffs with known tempo, key and chords, for testing."""

from __future__ import annotations

import io

import numpy as np
from scipy.io import wavfile

SR = 44100

# Open-position guitar voicings (MIDI note numbers, low string first).
VOICINGS = {
    "G": [43, 47, 50, 55, 59, 67],
    "C": [48, 52, 55, 60, 64],
    "D": [50, 57, 62, 66],
    "Em": [40, 47, 52, 55, 59, 64],
    "Am": [45, 52, 57, 60, 64],
    "E": [40, 47, 52, 56, 59, 64],
    "A": [45, 52, 57, 61, 64],
    "F": [41, 48, 53, 57, 60, 65],
    "Dm": [50, 57, 62, 65],
}


def pluck(midi: float, seconds: float, sr: int = SR, amp: float = 1.0) -> np.ndarray:
    """A plucked-string-like tone: decaying harmonics, brighter at the start."""
    f0 = 440.0 * 2 ** ((midi - 69) / 12)
    t = np.arange(int(seconds * sr)) / sr
    out = np.zeros_like(t)
    for k in range(1, 9):
        if f0 * k > sr / 2:
            break
        decay = 1.2 + 0.9 * k
        out += (1 / k) * np.sin(2 * np.pi * f0 * k * t) * np.exp(-decay * t)
    attack = np.minimum(1.0, t / 0.003)
    return amp * out * attack


def render(events: list[tuple[float, float, float, float]], total: float, sr: int = SR) -> np.ndarray:
    """events: (start_seconds, midi, length_seconds, amplitude)."""
    out = np.zeros(int(total * sr) + sr)
    for start, midi, length, amp in events:
        tone = pluck(midi, length, sr, amp)
        i = int(start * sr)
        out[i : i + len(tone)] += tone[: len(out) - i]
    return out[: int(total * sr)]


def strummed(
    progression: list[str],
    bpm: float,
    beats_per_chord: int = 4,
    repeats: int = 1,
    lead_in: float = 0.4,
    pickup: bool = False,
    jitter: float = 0.0,
) -> np.ndarray:
    """Down-strum every beat, accenting beat 1 of each chord.

    `jitter` adds random timing errors (in seconds) to each strum, like a
    person playing without a click track.
    """
    rng = np.random.default_rng(1)
    beat = 60 / bpm
    events = []
    t = lead_in
    if pickup:
        # A single quiet note one beat before bar 1.
        events.append((t, 55, beat, 0.4))
        t += beat
    for _ in range(repeats):
        for name in progression:
            for b in range(beats_per_chord):
                accent = 1.0 if b == 0 else 0.6
                offset = rng.uniform(-jitter, jitter) if jitter else 0.0
                for i, note in enumerate(VOICINGS[name]):
                    events.append((t + offset + i * 0.012, note, beat * 1.6, accent / len(VOICINGS[name]) * 3))
                t += beat
    return render(events, t + 0.8)


def melody(notes: list[int], bpm: float, lead_in: float = 0.3) -> np.ndarray:
    """One note per beat."""
    beat = 60 / bpm
    events = [(lead_in + i * beat, n, beat * 1.3, 0.8 if i % 4 == 0 else 0.6) for i, n in enumerate(notes)]
    return render(events, lead_in + len(notes) * beat + 0.6)


def to_wav(x: np.ndarray, sr: int = SR, stereo_left_only: bool = False, noise: float = 0.002) -> bytes:
    rng = np.random.default_rng(0)
    x = x / (np.max(np.abs(x)) + 1e-9) * 0.7 + rng.normal(0, noise, len(x))
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    if stereo_left_only:
        right = (rng.normal(0, noise, len(x)) * 32767).astype(np.int16)
        pcm = np.stack([pcm, right], axis=1)
    buf = io.BytesIO()
    wavfile.write(buf, sr, pcm)
    return buf.getvalue()
