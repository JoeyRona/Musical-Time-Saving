import pytest

from riffback.analysis import ChordEvent
from riffback.arrange import BASS_HIGH, BASS_LOW, BASS_STYLES, DRUM_STYLES, arrange
from riffback.midi import PPQ, _varlen, to_midi

from .midi_reader import parse

# G | D | Em C (Em and C get two beats each)
CHORDS = [
    ChordEvent(0, 0, 4, 7, "maj", "G"),
    ChordEvent(1, 0, 4, 2, "maj", "D"),
    ChordEvent(2, 0, 2, 4, "min", "Em"),
    ChordEvent(2, 2, 2, 0, "maj", "C"),
]


@pytest.mark.parametrize("drum_style", DRUM_STYLES)
@pytest.mark.parametrize("bass_style", BASS_STYLES)
def test_every_style_combination_produces_notes(drum_style, bass_style):
    arr = arrange(CHORDS, bars=3, tempo=100, drum_style=drum_style, bass_style=bass_style, repeats=2)
    assert arr.total_beats == 24
    for track in ("drums", "bass", "keys"):
        assert arr.track(track), f"{track} is empty"
    assert all(1 <= n.velocity <= 127 for n in arr.notes)
    # Nothing (except the final crash) starts after the end.
    assert max(n.start for n in arr.track("bass")) < arr.total_beats


@pytest.mark.parametrize("bass_style", BASS_STYLES)
def test_bass_stays_in_bass_range(bass_style):
    arr = arrange(CHORDS, bars=3, tempo=100, bass_style=bass_style)
    pitches = [n.pitch for n in arr.track("bass")]
    assert min(pitches) >= BASS_LOW - 1
    assert max(pitches) <= BASS_HIGH + 7


def test_bass_plays_the_chord_root_on_each_change():
    arr = arrange(CHORDS, bars=3, tempo=100, bass_style="roots", repeats=1, humanize=False)
    by_beat = {n.start: n.pitch % 12 for n in arr.track("bass")}
    assert by_beat[0] == 7  # G
    assert by_beat[4] == 2  # D
    assert by_beat[8] == 4  # E
    assert by_beat[10] == 0  # C


def test_walking_bass_approaches_next_root_from_below():
    arr = arrange(CHORDS, bars=3, tempo=100, bass_style="walking", repeats=1)
    by_beat = {n.start: n.pitch for n in arr.track("bass")}
    assert (by_beat[3] + 1) % 12 == 2  # beat before D is C#


def test_keys_voice_leading_keeps_parts_close():
    arr = arrange(CHORDS, bars=3, tempo=100, repeats=1)
    keys = arr.track("keys")
    assert len(keys) == 12  # 4 chords x 3 notes
    assert all(50 <= n.pitch <= 72 for n in keys)


def test_invalid_styles_are_rejected():
    with pytest.raises(ValueError):
        arrange(CHORDS, bars=3, tempo=100, drum_style="polka")
    with pytest.raises(ValueError):
        arrange(CHORDS, bars=3, tempo=100, bass_style="slap")
    with pytest.raises(ValueError):
        arrange([], bars=3, tempo=100)


@pytest.mark.parametrize(
    "value, encoded",
    [(0, b"\x00"), (127, b"\x7f"), (128, b"\x81\x00"), (480, b"\x83\x60"), (0x3FFF, b"\xff\x7f")],
)
def test_variable_length_encoding(value, encoded):
    assert _varlen(value) == encoded


def test_midi_file_round_trip():
    arr = arrange(CHORDS, bars=3, tempo=96, repeats=1)
    midi = parse(to_midi(arr))

    assert midi.format == 1 and midi.ppq == PPQ
    conductor, drums, bass, keys = midi.tracks
    assert conductor.tempo_usec == round(60_000_000 / 96)
    assert conductor.time_signature == (4, 4)
    assert [drums.name, bass.name, keys.name] == ["Drums", "Bass", "Keys"]
    assert {ch for _, _, ch, _, _ in drums.notes} == {9}  # GM drum channel

    for track, part in ((drums, "drums"), (bass, "bass"), (keys, "keys")):
        ons = [n for n in track.notes if n[1] == "on"]
        offs = [n for n in track.notes if n[1] == "off"]
        assert len(ons) == len(offs) == len(arr.track(part))

    first_bass = min(n for n in bass.notes if n[1] == "on")
    assert first_bass[0] == 0 and first_bass[3] % 12 == 7  # G on the downbeat


def test_single_part_export():
    arr = arrange(CHORDS, bars=3, tempo=120)
    midi = parse(to_midi(arr, ["bass"]))
    assert [t.name for t in midi.tracks[1:]] == ["Bass"]
    with pytest.raises(ValueError):
        to_midi(arr, ["vocals"])
