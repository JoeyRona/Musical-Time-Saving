"""Loading and cleaning up recorded audio."""

from __future__ import annotations

import io
from dataclasses import dataclass
from math import gcd

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

TARGET_SR = 22050
MIN_SECONDS = 2.0
MAX_SECONDS = 90.0


class AudioError(ValueError):
    """Raised when an upload can't be used (wrong format, too short, silent...)."""


@dataclass
class Audio:
    samples: np.ndarray  # mono float32 in [-1, 1]
    sr: int
    trim_offset: float  # seconds of silence removed from the start of the original

    @property
    def duration(self) -> float:
        return len(self.samples) / self.sr


def _to_float(data: np.ndarray) -> np.ndarray:
    if data.dtype == np.uint8:
        return (data.astype(np.float32) - 128.0) / 128.0
    if np.issubdtype(data.dtype, np.integer):
        return data.astype(np.float32) / float(np.iinfo(data.dtype).max)
    return data.astype(np.float32)


def _to_mono(data: np.ndarray) -> np.ndarray:
    if data.ndim == 1:
        return data
    # Audio interfaces often put the guitar on one channel only (input 1 =
    # left), with the other channel silent or just noise. If one channel is
    # much louder, use it instead of averaging the guitar with noise.
    energy = np.sqrt(np.mean(data**2, axis=0)) + 1e-12
    loudest = int(np.argmax(energy))
    if energy[loudest] > 4 * np.min(energy):
        return data[:, loudest]
    return data.mean(axis=1)


def _frame_rms(x: np.ndarray, frame: int) -> np.ndarray:
    n = len(x) // frame
    if n == 0:
        return np.array([np.sqrt(np.mean(x**2))]) if len(x) else np.zeros(1)
    return np.sqrt(np.mean(x[: n * frame].reshape(n, frame) ** 2, axis=1))


def load_wav(data: bytes) -> Audio:
    """Decode a WAV file and return trimmed, normalised mono audio at TARGET_SR."""
    try:
        sr, raw = wavfile.read(io.BytesIO(data))
    except Exception as exc:  # scipy raises several different error types
        raise AudioError("Couldn't read that file. Please upload a WAV recording.") from exc

    if raw.size == 0:
        raise AudioError("The recording is empty.")

    x = _to_mono(_to_float(raw))
    if sr != TARGET_SR:
        g = gcd(int(sr), TARGET_SR)
        x = resample_poly(x, TARGET_SR // g, int(sr) // g).astype(np.float32)

    peak = float(np.max(np.abs(x)))
    if peak < 1e-3:
        raise AudioError("The recording is silent. Check your input device and gain.")
    x = x / peak

    # Trim silence (anything 40 dB below the loudest part) from both ends.
    frame = 512
    rms = _frame_rms(x, frame)
    loud = np.nonzero(rms > rms.max() * 10 ** (-40 / 20))[0]
    start = max(int(loud[0]) - 1, 0) * frame
    end = min((int(loud[-1]) + 2) * frame, len(x))
    x = x[start:end]

    duration = len(x) / TARGET_SR
    if duration < MIN_SECONDS:
        raise AudioError(f"The riff is too short ({duration:.1f}s). Record at least {MIN_SECONDS:.0f} seconds.")
    if duration > MAX_SECONDS:
        raise AudioError(f"The recording is too long ({duration:.0f}s). Keep it under {MAX_SECONDS:.0f} seconds.")

    return Audio(samples=x.astype(np.float32), sr=TARGET_SR, trim_offset=start / TARGET_SR)
