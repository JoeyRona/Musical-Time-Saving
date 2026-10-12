// Types and calls for the RiffBack backend (see backend/riffback/api.py).

export type Quality = "maj" | "min";

export interface ChordEvent {
  bar: number;
  beat: number;
  beats: number;
  root: number; // pitch class, C = 0
  quality: Quality;
  name: string;
}

export interface Analysis {
  tempo: number;
  key: string;
  key_tonic: number;
  key_mode: "major" | "minor";
  key_confidence: number;
  tuning_cents: number;
  duration: number;
  beats_per_bar: number;
  bars: number;
  first_downbeat: number;
  beat_times: number[];
  chords: ChordEvent[];
}

export const DRUM_STYLES = ["rock", "halftime", "ballad", "four-on-floor"] as const;
export const BASS_STYLES = ["roots", "eighths", "root-fifth", "walking"] as const;
export type DrumStyle = (typeof DRUM_STYLES)[number];
export type BassStyle = (typeof BASS_STYLES)[number];
export type Part = "all" | "drums" | "bass" | "keys";

export interface BandSettings {
  drum_style: DrumStyle;
  bass_style: BassStyle;
  repeats: number;
}

export interface Note {
  track: "drums" | "bass" | "keys";
  start: number; // beats from bar 1
  duration: number; // beats
  pitch: number;
  velocity: number;
}

export interface Arrangement {
  tempo: number;
  beats_per_bar: number;
  total_beats: number;
  notes: Note[];
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    // not JSON
  }
  return `The server returned an error (${res.status}).`;
}

async function call(path: string, init: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new Error("Can't reach the RiffBack server. Is the backend running on port 8000?");
  }
  if (!res.ok) throw new Error(await errorMessage(res));
  return res;
}

export async function analyzeRiff(wav: Blob, tempoHint?: number): Promise<Analysis> {
  const form = new FormData();
  form.append("file", wav, "riff.wav");
  const query = tempoHint ? `?tempo_hint=${tempoHint.toFixed(2)}` : "";
  const res = await call(`/api/analyze${query}`, { method: "POST", body: form });
  return res.json();
}

function requestBody(analysis: Analysis, chords: ChordEvent[], band: BandSettings): string {
  return JSON.stringify({
    tempo: analysis.tempo,
    bars: analysis.bars,
    beats_per_bar: analysis.beats_per_bar,
    chords,
    ...band,
  });
}

export async function getArrangement(analysis: Analysis, chords: ChordEvent[], band: BandSettings): Promise<Arrangement> {
  const res = await call("/api/arrangement", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: requestBody(analysis, chords, band),
  });
  return res.json();
}

export async function downloadMidi(analysis: Analysis, chords: ChordEvent[], band: BandSettings, part: Part): Promise<void> {
  const res = await call(`/api/midi?part=${part}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: requestBody(analysis, chords, band),
  });
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `riffback-${part}.mid`;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
