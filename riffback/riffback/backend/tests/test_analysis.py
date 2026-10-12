import pytest

from riffback.analysis import analyze
from riffback.audio import AudioError, load_wav

from .synth import melody, strummed, to_wav


def chords_by_bar(result):
    """Chord name at beat 1 of each bar, e.g. ['G', 'D', 'Em', 'C']."""
    names = {}
    for ev in result.chords:
        if ev.beat == 0:
            names[ev.bar] = ev.name
    return [names.get(b) for b in range(result.bars)]


def run(x, **kwargs):
    return analyze(load_wav(to_wav(x)), **kwargs)


@pytest.mark.parametrize("bpm", [72, 85, 100, 120])
def test_tempo_is_detected(bpm):
    result = run(strummed(["G", "C", "D", "G"], bpm, repeats=2))
    assert result.tempo == pytest.approx(bpm, rel=0.04)


def test_chords_and_key_for_a_pop_progression():
    result = run(strummed(["G", "D", "Em", "C"], 100, repeats=2))
    assert result.key == "G major"
    assert result.bars == 8
    assert chords_by_bar(result) == ["G", "D", "Em", "C"] * 2


def test_key_uses_chords_not_just_overtones():
    # Raw chroma of this progression leans towards G; Dm settles it as C.
    result = run(strummed(["C", "Am", "Dm", "G"], 80))
    assert result.key == "C major"
    assert chords_by_bar(result) == ["C", "Am", "Dm", "G"]


def test_minor_key_melody():
    # One note per beat outlining Am | G | F | E (a classic minor riff).
    notes = [69, 72, 76, 72, 67, 71, 74, 71, 65, 69, 72, 69, 64, 68, 71, 76]
    result = run(melody(notes, 90))
    assert result.key == "A minor"
    assert chords_by_bar(result) == ["Am", "G", "F", "E"]


def test_handles_loose_human_timing():
    result = run(strummed(["Am", "F", "C", "G"], 90, repeats=2, jitter=0.02))
    assert result.tempo == pytest.approx(90, rel=0.04)
    assert chords_by_bar(result) == ["Am", "F", "C", "G"] * 2


def test_pickup_note_is_not_mistaken_for_bar_one():
    result = run(strummed(["G", "Em", "C", "D"], 95, pickup=True))
    assert chords_by_bar(result) == ["G", "Em", "C", "D"]
    # bar 1 starts one beat (0.63 s) after the pickup note
    assert result.first_downbeat == pytest.approx(result.beat_times[1], abs=1e-3)


def test_tempo_hint_fixes_half_time_detection():
    x = strummed(["G", "C", "D", "G"], 140, repeats=2)
    assert run(x, tempo_hint=140).tempo == pytest.approx(140, rel=0.04)


def test_guitar_on_left_channel_only():
    wav = to_wav(strummed(["E", "A", "E", "A"], 100), stereo_left_only=True)
    result = analyze(load_wav(wav))
    assert result.key == "E major"


def test_beat_times_are_relative_to_the_original_file():
    result = run(strummed(["G", "D"], 100, lead_in=1.0))
    assert result.first_downbeat == pytest.approx(1.0, abs=0.06)


@pytest.mark.parametrize(
    "data, message",
    [
        (b"not audio", "WAV"),
        (to_wav(strummed(["G"], 120, beats_per_chord=1)), "too short"),
    ],
)
def test_bad_audio_is_rejected(data, message):
    with pytest.raises(AudioError, match=message):
        load_wav(data)


def test_silence_is_rejected():
    import io

    import numpy as np
    from scipy.io import wavfile

    buf = io.BytesIO()
    wavfile.write(buf, 44100, np.zeros(44100 * 3, dtype=np.int16))
    with pytest.raises(AudioError, match="silent"):
        load_wav(buf.getvalue())
