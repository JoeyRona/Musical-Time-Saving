"""Tempo, beat, key and chord detection for a short recorded riff.

Pipeline
--------
1. Onset envelope   - spectral flux: how much new energy appears in each frame.
2. Tempo            - autocorrelation of the onset envelope, with a prior that
                      prefers tempos around 100 BPM to avoid half/double errors.
3. Beats            - dynamic-programming beat tracker (Ellis, 2007), which
                      copes with the small tempo drift of playing without a click.
4. Chroma           - energy in each of the 12 pitch classes, tuning-corrected.
5. Key              - correlation with Krumhansl-Kessler key profiles.
6. Chords           - template matching per half bar, smoothed with Viterbi
                      decoding so chords don't flicker between similar shapes.

Only NumPy and SciPy are used, so every step can be read and explained.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
from scipy.ndimage import uniform_filter1d

from .audio import Audio
from .theory import Chord, Key, chord_templates, key_profiles

HOP = 512
ONSET_FFT = 2048
CHROMA_FFT = 8192
BEATS_PER_BAR = 4
BEATS_PER_CHORD_SLOT = 2  # chords can change every half bar
MIN_BPM, MAX_BPM = 50.0, 200.0
PREFERRED_BPM = 100.0


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


@dataclass
class ChordEvent:
    bar: int  # 0-based bar index (bar 0 starts at the first downbeat)
    beat: int  # beat within the bar where the chord starts (0-3)
    beats: int  # length in beats
    root: int
    quality: str
    name: str


@dataclass
class Analysis:
    tempo: float
    key: str
    key_tonic: int
    key_mode: str
    key_confidence: float  # 0-1, how clearly the best key beat the runner-up
    tuning_cents: float  # how far the guitar is from A440 tuning
    duration: float  # seconds of audio after trimming silence
    beats_per_bar: int
    bars: int
    first_downbeat: float  # seconds into the ORIGINAL upload where bar 1 starts
    beat_times: list[float]  # seconds into the original upload
    chords: list[ChordEvent] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Spectral helpers
# --------------------------------------------------------------------------


def _stft_magnitude(x: np.ndarray, n_fft: int, hop: int = HOP) -> np.ndarray:
    """Magnitude spectrogram, shape (frames, n_fft // 2 + 1), frames centred on hop*i."""
    pad = n_fft // 2
    padded = np.pad(x, (pad, pad))
    n_frames = 1 + (len(padded) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(n_frames)[:, None]
    frames = padded[idx] * np.hanning(n_fft)[None, :]
    return np.abs(np.fft.rfft(frames, axis=1))


def onset_envelope(x: np.ndarray, sr: int) -> np.ndarray:
    """Spectral flux: summed positive change in log-magnitude, one value per frame."""
    mag = _stft_magnitude(x, ONSET_FFT)
    freqs = np.fft.rfftfreq(ONSET_FFT, 1 / sr)
    mag = mag[:, (freqs > 40) & (freqs < 8000)]
    log_mag = np.log1p(100 * mag)
    flux = np.maximum(0.0, np.diff(log_mag, axis=0)).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    # Remove the slowly varying part so only the "spikes" of new notes remain.
    flux = np.maximum(0.0, flux - uniform_filter1d(flux, size=16))
    peak = flux.max()
    return flux / peak if peak > 0 else flux


# --------------------------------------------------------------------------
# Tempo and beats
# --------------------------------------------------------------------------


def estimate_tempo(onset: np.ndarray, sr: int) -> float:
    """Most likely tempo in BPM from the autocorrelation of the onset envelope."""
    frame_rate = sr / HOP
    env = onset - onset.mean()
    ac = np.correlate(env, env, mode="full")[len(env) - 1 :]
    if ac[0] <= 0:
        return PREFERRED_BPM
    ac = ac / ac[0]

    min_lag = int(np.floor(60 * frame_rate / MAX_BPM))
    max_lag = min(int(np.ceil(60 * frame_rate / MIN_BPM)), len(ac) // 2 - 1)
    if max_lag <= min_lag + 2:
        return PREFERRED_BPM

    lags = np.arange(min_lag, max_lag + 1)
    bpms = 60 * frame_rate / lags
    # A beat period should also line up with 2 and 4 beats later, so add those
    # in. This favours the "real" beat over random repetitions.
    score = ac[lags].copy()
    for mult, w in ((2, 0.5), (4, 0.25)):
        ok = lags * mult < len(ac)
        score[ok] += w * ac[lags[ok] * mult]
    # Log-normal prior around PREFERRED_BPM (one octave standard deviation).
    prior = np.exp(-0.5 * (np.log2(bpms / PREFERRED_BPM) / 1.0) ** 2)
    weighted = np.maximum(score, 0) * prior

    i = int(np.argmax(weighted))
    # Parabolic interpolation for sub-frame precision.
    if 0 < i < len(weighted) - 1:
        a, b, c = weighted[i - 1], weighted[i], weighted[i + 1]
        denom = a - 2 * b + c
        offset = 0.5 * (a - c) / denom if denom != 0 else 0.0
    else:
        offset = 0.0
    return float(60 * frame_rate / (lags[i] + offset))


def track_beats(onset: np.ndarray, sr: int, bpm: float, tightness: float = 100.0) -> np.ndarray:
    """Dynamic-programming beat tracker. Returns beat positions in frames.

    Each frame's score is its onset strength plus the best score of a previous
    beat roughly one period earlier, penalised for deviating from the period.
    Backtracking from the best final frame gives the beat sequence.
    """
    period = 60 * sr / HOP / bpm
    n = len(onset)
    # Smooth the onset envelope with a Gaussian about a beat-fraction wide.
    width = max(1, int(round(period / 16)))
    kernel = np.exp(-0.5 * (np.arange(-4 * width, 4 * width + 1) / width) ** 2)
    local = np.convolve(onset, kernel, mode="same")
    local = local / (local.max() + 1e-9)

    score = local.copy()
    backlink = np.full(n, -1, dtype=int)
    lo, hi = int(round(period / 2)), int(round(period * 2))
    offsets = np.arange(lo, hi + 1)
    penalty = -tightness * np.log(offsets / period) ** 2

    for t in range(lo, n):
        prev = t - offsets
        valid = prev >= 0
        if not valid.any():
            continue
        candidates = score[prev[valid]] + penalty[valid]
        j = int(np.argmax(candidates))
        score[t] = local[t] + candidates[j]
        backlink[t] = prev[valid][j]

    # Start backtracking from the strongest score in the last beat period.
    tail = max(0, n - int(round(period)))
    t = tail + int(np.argmax(score[tail:]))
    beats = [t]
    while backlink[t] >= 0:
        t = backlink[t]
        beats.append(t)
    beats = np.array(beats[::-1], dtype=float)

    # Extend the grid to cover the start and end of the riff.
    while beats[0] - period > -period / 4:
        beats = np.concatenate([[max(beats[0] - period, 0.0)], beats])
        if beats[0] == 0.0:
            break
    while beats[-1] + period < n - period / 4:
        beats = np.append(beats, beats[-1] + period)
    return beats


# --------------------------------------------------------------------------
# Chroma
# --------------------------------------------------------------------------


def _estimate_tuning(mag: np.ndarray, freqs: np.ndarray) -> float:
    """Average deviation (in semitones) of strong spectral peaks from A440 pitches."""
    spectrum = mag.mean(axis=0)
    band = (freqs > 70) & (freqs < 1200)
    s = spectrum.copy()
    s[~band] = 0
    is_peak = (s[1:-1] > s[:-2]) & (s[1:-1] > s[2:]) & (s[1:-1] > s.max() * 0.05)
    peaks = np.nonzero(is_peak)[0] + 1
    if len(peaks) < 3:
        return 0.0
    # Refine each peak frequency with parabolic interpolation.
    a, b, c = s[peaks - 1], s[peaks], s[peaks + 1]
    denom = a - 2 * b + c
    delta = np.where(denom != 0, 0.5 * (a - c) / np.where(denom == 0, 1, denom), 0)
    f = (peaks + delta) * (freqs[1] - freqs[0])
    midi = 69 + 12 * np.log2(f / 440.0)
    dev = midi - np.round(midi)
    # Circular mean so deviations near +/-0.5 don't cancel out.
    angle = np.angle(np.sum(b * np.exp(2j * np.pi * dev)))
    return float(angle / (2 * np.pi))


def chromagram(x: np.ndarray, sr: int) -> tuple[np.ndarray, float]:
    """Pitch-class energy per frame, shape (frames, 12), plus tuning offset in semitones."""
    mag = _stft_magnitude(x, CHROMA_FFT)
    freqs = np.fft.rfftfreq(CHROMA_FFT, 1 / sr)
    tuning = _estimate_tuning(mag, freqs)

    band = (freqs >= 65) & (freqs <= 1600)
    f = freqs[band]
    m = mag[:, band]

    # Keep only spectral peaks (the actual notes and their harmonics) that are
    # within 40 dB of the loudest peak in the frame. Using every bin would let
    # background noise - spread over thousands of bins - flatten the chroma.
    is_peak = np.zeros_like(m, dtype=bool)
    is_peak[:, 1:-1] = (m[:, 1:-1] > m[:, :-2]) & (m[:, 1:-1] >= m[:, 2:])
    frame_max = m.max(axis=1, keepdims=True) + 1e-12
    is_peak &= m > frame_max * 0.01
    # Compress dynamics so a loud low string doesn't drown out the rest.
    peaks = np.where(is_peak, np.sqrt(m / frame_max), 0.0)
    # Quiet frames (between notes) should count less than loud ones.
    peaks *= np.sqrt(frame_max / (frame_max.max() + 1e-12))

    midi = 69 + 12 * np.log2(f / 440.0) - tuning
    nearest = np.round(midi)
    # Weight each bin by how close it is to a real semitone, so energy that
    # sits between two notes (leakage, string bends) counts less.
    weight = np.clip(1 - 2 * np.abs(midi - nearest), 0, 1)
    pc = nearest.astype(int) % 12
    mapping = np.zeros((len(f), 12))
    mapping[np.arange(len(f)), pc] = weight
    return peaks @ mapping, tuning * 100


def beat_sync(chroma: np.ndarray, beats: np.ndarray) -> np.ndarray:
    """Average chroma between consecutive beats -> shape (len(beats), 12)."""
    edges = np.append(np.round(beats).astype(int), len(chroma))
    out = np.zeros((len(beats), 12))
    for i in range(len(beats)):
        a, b = edges[i], max(edges[i + 1], edges[i] + 1)
        out[i] = chroma[a:b].mean(axis=0) if a < len(chroma) else 0
    return out


# --------------------------------------------------------------------------
# Key and chords
# --------------------------------------------------------------------------


def key_correlations(chroma_total: np.ndarray) -> tuple[list[Key], np.ndarray]:
    """Pearson correlation between the riff's overall chroma and all 24 key profiles."""
    keys, profiles = key_profiles()
    c = chroma_total - chroma_total.mean()
    p = profiles - profiles.mean(axis=1, keepdims=True)
    corr = (p @ c) / (np.linalg.norm(p, axis=1) * np.linalg.norm(c) + 1e-9)
    return keys, corr


def refine_key(keys: list[Key], corr: np.ndarray, slot_chords: list[Chord | None]) -> tuple[Key, float]:
    """Combine the chroma correlation with evidence from the detected chords.

    Overtones push the raw chroma towards the key a fifth above, so a riff in
    C can look like it's in G. Chords settle it: in C major, Dm is "allowed"
    but in G major it isn't. Songs also tend to start and end on the tonic.
    """
    played = [c for c in slot_chords if c is not None]
    if not played:
        best = int(np.argmax(corr))
        return keys[best], 0.0
    scores = corr.copy()
    for i, key in enumerate(keys):
        diatonic = key.diatonic_chords()
        fraction = np.mean([(c.root, c.quality) in diatonic for c in played])
        tonic = (key.tonic, "maj" if key.mode == "major" else "min")
        scores[i] += 0.5 * fraction
        scores[i] += 0.1 * ((played[0].root, played[0].quality) == tonic)
        scores[i] += 0.1 * ((played[-1].root, played[-1].quality) == tonic)
    order = np.argsort(scores)[::-1]
    margin = scores[order[0]] - scores[order[1]]
    return keys[int(order[0])], float(np.clip(margin / 0.2, 0, 1))


def choose_downbeat(sync: np.ndarray, beat_strength: np.ndarray) -> int:
    """Pick which of the first 4 beats is "beat 1", assuming 4/4.

    Harmony usually changes at bar lines, so for each candidate phase compare
    the two beats before each would-be bar line with the two beats after it.
    Comparing two-beat windows (rather than single beats) means a melody that
    outlines one chord per bar still reads as one harmony per bar. Accents and
    a small bonus for "the riff starts on beat 1" break ties.
    """
    n = len(sync)
    if n < 6:
        return 0
    halves = sync[:-1] + sync[1:]  # halves[i] = beats i and i+1
    halves = halves / (np.linalg.norm(halves, axis=1, keepdims=True) + 1e-9)
    scores = []
    for phase in range(BEATS_PER_BAR):
        lines = [i for i in range(phase, n - 1) if i >= 2 and i % BEATS_PER_BAR == phase]
        if not lines:
            scores.append(-np.inf)
            continue
        change = np.mean([1 - halves[i - 2] @ halves[i] for i in lines])
        accent = beat_strength[phase::BEATS_PER_BAR].mean()
        scores.append(change + 0.3 * accent + (0.05 if phase == 0 else 0.0))
    return int(np.argmax(scores))


def detect_chords(slot_chroma: np.ndarray, key: Key, switch_penalty: float = 0.15) -> list[Chord | None]:
    """Most likely chord for each slot, using Viterbi smoothing.

    Emission score: cosine similarity between the slot's chroma and each chord
    template, plus a small bonus for chords that belong to the detected key.
    Transition score: staying on the same chord is free, changing costs
    `switch_penalty`. Silent slots return None.
    """
    chords, templates = chord_templates()
    diatonic = key.diatonic_chords()
    bonus = np.array([0.06 if (c.root, c.quality) in diatonic else 0.0 for c in chords])

    energy = np.linalg.norm(slot_chroma, axis=1)
    norm = slot_chroma / (energy[:, None] + 1e-9)
    emission = norm @ templates.T + bonus[None, :]

    n, k = emission.shape
    score = emission[0].copy()
    back = np.zeros((n, k), dtype=int)
    stay = np.eye(k, dtype=bool)
    for t in range(1, n):
        trans = score[:, None] - switch_penalty * (~stay)
        back[t] = np.argmax(trans, axis=0)
        score = trans[back[t], np.arange(k)] + emission[t]
    path = [int(np.argmax(score))]
    for t in range(n - 1, 0, -1):
        path.append(int(back[t, path[-1]]))
    path.reverse()

    silent = energy < 0.1 * (energy.max() + 1e-9)
    return [None if silent[i] else chords[j] for i, j in enumerate(path)]


# --------------------------------------------------------------------------
# Full pipeline
# --------------------------------------------------------------------------


def analyze(audio: Audio, tempo_hint: float | None = None) -> Analysis:
    """Run the full pipeline. `tempo_hint` overrides the tempo estimate, e.g.
    when the user says the detected tempo is half or double what they played."""
    x, sr = audio.samples, audio.sr
    frame_rate = sr / HOP

    onset = onset_envelope(x, sr)
    bpm = float(np.clip(tempo_hint, 30, 300)) if tempo_hint else estimate_tempo(onset, sr)
    beats = track_beats(onset, sr, bpm)
    if len(beats) > 2:
        bpm = float(60 * frame_rate / np.median(np.diff(beats)))

    chroma, tuning_cents = chromagram(x, sr)
    sync = beat_sync(chroma, beats)
    beat_strength = onset[np.clip(np.round(beats).astype(int), 0, len(onset) - 1)]
    downbeat = choose_downbeat(sync, beat_strength)

    bar_beats = beats[downbeat:]
    bars = max(1, int(np.ceil(len(bar_beats) / BEATS_PER_BAR - 0.25)))
    total_beats = bars * BEATS_PER_BAR

    # Group beats into half-bar slots.
    sync_bars = sync[downbeat:]
    slots = []
    for s in range(0, total_beats, BEATS_PER_CHORD_SLOT):
        part = sync_bars[s : s + BEATS_PER_CHORD_SLOT]
        slots.append(part.mean(axis=0) if len(part) else np.zeros(12))
    slots = np.array(slots)

    # Pass 1: rough key from chroma alone -> chords.
    # Pass 2: better key using those chords -> final chords.
    keys, corr = key_correlations(chroma.sum(axis=0))
    rough_key = keys[int(np.argmax(corr))]
    key, key_conf = refine_key(keys, corr, detect_chords(slots, rough_key))
    slot_chords = detect_chords(slots, key)

    # Fill silent slots with the previous chord, then merge repeats.
    events: list[ChordEvent] = []
    last: Chord | None = None
    for i, chord in enumerate(slot_chords):
        chord = chord or last or next((c for c in slot_chords if c), None)
        if chord is None:
            continue
        start = i * BEATS_PER_CHORD_SLOT
        bar, beat = divmod(start, BEATS_PER_BAR)
        # Merge with the previous event if it's the same chord, but always
        # start a new event at a bar line so the chart reads bar by bar.
        if events and chord == last and beat != 0:
            events[-1].beats += BEATS_PER_CHORD_SLOT
        else:
            events.append(ChordEvent(bar, beat, BEATS_PER_CHORD_SLOT, chord.root, chord.quality, chord.name(key)))
        last = chord

    beat_times = (beats / frame_rate + audio.trim_offset).round(4).tolist()
    return Analysis(
        tempo=round(bpm, 1),
        key=key.name,
        key_tonic=key.tonic,
        key_mode=key.mode,
        key_confidence=round(key_conf, 2),
        tuning_cents=round(tuning_cents, 1),
        duration=round(audio.duration, 3),
        beats_per_bar=BEATS_PER_BAR,
        bars=bars,
        first_downbeat=round(float(beats[downbeat] / frame_rate + audio.trim_offset), 4),
        beat_times=beat_times,
        chords=events,
    )
