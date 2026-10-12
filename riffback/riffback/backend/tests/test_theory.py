import numpy as np

from riffback.theory import Chord, Key, chord_templates, key_profiles


def test_diatonic_chords_of_g_major():
    names = {Chord(r, q).name(Key(7, "major")) for r, q in Key(7, "major").diatonic_chords()}
    assert names == {"G", "Am", "Bm", "C", "D", "Em"}


def test_minor_key_includes_harmonic_minor_dominant():
    names = {Chord(r, q).name(Key(9, "minor")) for r, q in Key(9, "minor").diatonic_chords()}
    assert {"Am", "Dm", "Em", "E", "F", "G", "C"} == names


def test_flat_keys_are_spelled_with_flats():
    assert Key(5, "major").name == "F major"
    assert Chord(10, "maj").name(Key(5, "major")) == "Bb"
    assert Chord(10, "maj").name(Key(11, "major")) == "A#"
    assert Key(0, "minor").name == "C minor"
    assert Chord(3, "maj").name(Key(0, "minor")) == "Eb"


def test_templates_are_unit_length_and_cover_all_triads():
    chords, templates = chord_templates()
    assert len(chords) == 24
    assert np.allclose(np.linalg.norm(templates, axis=1), 1)
    # The C major template should peak on C, E and G.
    c_major = templates[chords.index(Chord(0, "maj"))]
    assert set(np.argsort(c_major)[-3:]) == {0, 4, 7}


def test_key_profiles_rotate_with_tonic():
    keys, profiles = key_profiles()
    d_major = profiles[keys.index(Key(2, "major"))]
    assert int(np.argmax(d_major)) == 2
