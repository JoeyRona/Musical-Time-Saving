"""HTTP API.

POST /api/analyze      upload a WAV  -> tempo, key, chords, beat grid
POST /api/arrangement  analysis + styles -> note list (for in-browser preview)
POST /api/midi         analysis + styles -> .mid file to drag into a DAW

The API is stateless: the browser keeps the analysis and sends it back, so
changing the drum or bass style doesn't need the audio re-analysed.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .analysis import ChordEvent, analyze
from .arrange import Arrangement, arrange
from .audio import AudioError, load_wav
from .midi import to_midi

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

app = FastAPI(
    title="RiffBack",
    version=__version__,
    description="Turn a guitar riff into a drum and bass backing track.",
)

# During development the Vite dev server proxies /api, so CORS is only needed
# if you host the frontend somewhere else (set ALLOWED_ORIGINS).
origins = [o for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------


class ChordOut(BaseModel):
    bar: int = Field(ge=0)
    beat: int = Field(ge=0, le=15)
    beats: int = Field(ge=1, le=64)
    root: int = Field(ge=0, le=11)
    quality: Literal["maj", "min"]
    name: str


class AnalysisOut(BaseModel):
    tempo: float
    key: str
    key_tonic: int
    key_mode: Literal["major", "minor"]
    key_confidence: float
    tuning_cents: float
    duration: float
    beats_per_bar: int
    bars: int
    first_downbeat: float
    beat_times: list[float]
    chords: list[ChordOut]


class ArrangementRequest(BaseModel):
    tempo: float = Field(gt=20, lt=400)
    bars: int = Field(ge=1, le=64)
    beats_per_bar: int = Field(default=4, ge=2, le=12)
    chords: list[ChordOut] = Field(min_length=1)
    drum_style: Literal["rock", "halftime", "ballad", "four-on-floor"] = "rock"
    bass_style: Literal["roots", "eighths", "root-fifth", "walking"] = "roots"
    repeats: int = Field(default=2, ge=1, le=16)


class NoteOut(BaseModel):
    track: str
    start: float
    duration: float
    pitch: int
    velocity: int


class ArrangementOut(BaseModel):
    tempo: float
    beats_per_bar: int
    total_beats: int
    notes: list[NoteOut]


def _build(req: ArrangementRequest) -> Arrangement:
    chords = [ChordEvent(c.bar, c.beat, c.beats, c.root, c.quality, c.name) for c in req.chords]
    try:
        return arrange(
            chords,
            bars=req.bars,
            tempo=req.tempo,
            drum_style=req.drum_style,
            bass_style=req.bass_style,
            repeats=req.repeats,
            beats_per_bar=req.beats_per_bar,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/api/analyze", response_model=AnalysisOut)
def analyze_riff(
    file: Annotated[UploadFile, File(description="A WAV recording of the riff")],
    tempo_hint: Annotated[float | None, Query(gt=20, lt=400, description="Override the detected tempo (BPM)")] = None,
) -> dict:
    # Plain `def` (not async): FastAPI runs it in a thread pool, so the
    # CPU-heavy analysis doesn't block other requests.
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large (25 MB max).")
    try:
        audio = load_wav(data)
    except AudioError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return analyze(audio, tempo_hint=tempo_hint).to_dict()


@app.post("/api/arrangement", response_model=ArrangementOut)
def arrangement(req: ArrangementRequest) -> dict:
    return _build(req).to_dict()


@app.post("/api/midi", response_class=Response, responses={200: {"content": {"audio/midi": {}}}})
def midi(
    req: ArrangementRequest,
    part: Annotated[Literal["all", "drums", "bass", "keys"], Query()] = "all",
) -> Response:
    arr = _build(req)
    parts = None if part == "all" else [part]
    filename = f"riffback-{part}-{round(req.tempo)}bpm.mid"
    return Response(
        content=to_midi(arr, parts),
        media_type="audio/midi",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Serve the built React app (frontend/dist) from the same server, so the
# whole thing can be deployed as one service.
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
