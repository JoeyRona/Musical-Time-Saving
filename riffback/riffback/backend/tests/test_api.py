import pytest
from fastapi.testclient import TestClient

from riffback.api import app

from .midi_reader import parse
from .synth import strummed, to_wav

client = TestClient(app)


@pytest.fixture(scope="module")
def analysis():
    wav = to_wav(strummed(["G", "D", "Em", "C"], 100))
    res = client.post("/api/analyze", files={"file": ("riff.wav", wav, "audio/wav")})
    assert res.status_code == 200, res.text
    return res.json()


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_analyze_returns_tempo_key_and_chords(analysis):
    assert analysis["tempo"] == pytest.approx(100, rel=0.04)
    assert analysis["key"] == "G major"
    assert [c["name"] for c in analysis["chords"] if c["beat"] == 0] == ["G", "D", "Em", "C"]
    assert len(analysis["beat_times"]) >= 16


def test_analyze_with_tempo_hint():
    wav = to_wav(strummed(["G", "C", "D", "G"], 140, repeats=2))
    res = client.post("/api/analyze?tempo_hint=140", files={"file": ("riff.wav", wav, "audio/wav")})
    assert res.json()["tempo"] == pytest.approx(140, rel=0.04)


def test_analyze_rejects_non_wav():
    res = client.post("/api/analyze", files={"file": ("riff.mp3", b"ID3 not really", "audio/mpeg")})
    assert res.status_code == 400
    assert "WAV" in res.json()["detail"]


def test_analyze_requires_a_file():
    assert client.post("/api/analyze").status_code == 422


def _request(analysis, **overrides):
    body = {k: analysis[k] for k in ("tempo", "bars", "beats_per_bar", "chords")}
    body.update(overrides)
    return body


def test_arrangement_preview(analysis):
    res = client.post("/api/arrangement", json=_request(analysis, drum_style="ballad", bass_style="walking"))
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total_beats"] == analysis["bars"] * 4 * 2
    assert {n["track"] for n in data["notes"]} == {"drums", "bass", "keys"}


def test_arrangement_validates_styles(analysis):
    res = client.post("/api/arrangement", json=_request(analysis, drum_style="polka"))
    assert res.status_code == 422


@pytest.mark.parametrize("part, expected_tracks", [("all", 4), ("bass", 2), ("drums", 2)])
def test_midi_download(analysis, part, expected_tracks):
    res = client.post(f"/api/midi?part={part}", json=_request(analysis))
    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/midi"
    assert "attachment" in res.headers["content-disposition"]
    midi = parse(res.content)
    assert len(midi.tracks) == expected_tracks
