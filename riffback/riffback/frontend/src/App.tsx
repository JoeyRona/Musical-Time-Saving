import { useCallback, useEffect, useRef, useState } from "react";
import {
  type Analysis,
  analyzeRiff,
  type Arrangement,
  type BandSettings,
  type ChordEvent,
  downloadMidi,
  getArrangement,
  type Part,
} from "./api";
import { DEFAULT_MIX, type Mix, Preview, type Track } from "./audio/preview";
import { BandPanel } from "./components/BandPanel";
import { ChordChart } from "./components/ChordChart";
import { ExportPanel } from "./components/ExportPanel";
import { RecordPanel } from "./components/RecordPanel";
import { usesFlats } from "./music";

const DEFAULT_BAND: BandSettings = { drum_style: "rock", bass_style: "roots", repeats: 2 };

function describeKey(a: Analysis): string {
  if (a.key_confidence >= 0.5) return a.key;
  return `${a.key} (probably)`;
}

function describeTuning(cents: number): string | null {
  if (Math.abs(cents) < 15) return null;
  return `Your guitar is about ${Math.abs(Math.round(cents))} cents ${cents > 0 ? "sharp" : "flat"}. The band is tuned to A440, so you may want to retune before recording over it.`;
}

export default function App() {
  const [wav, setWav] = useState<Blob | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [chords, setChords] = useState<ChordEvent[]>([]);
  const [band, setBand] = useState<BandSettings>(DEFAULT_BAND);
  const [arrangement, setArrangement] = useState<Arrangement | null>(null);
  const [mix, setMix] = useState<Mix>(DEFAULT_MIX);
  const [analyzing, setAnalyzing] = useState(false);
  const [arranging, setArranging] = useState(false);
  const [downloading, setDownloading] = useState<Part | null>(null);
  const [beat, setBeat] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const preview = useRef<Preview | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  const stopPreview = useCallback(() => {
    preview.current?.stop();
    setBeat(null);
  }, []);

  const runAnalysis = async (audio: Blob, tempoHint?: number) => {
    stopPreview();
    setAnalyzing(true);
    setError(null);
    try {
      const result = await analyzeRiff(audio, tempoHint);
      setWav(audio);
      setAnalysis(result);
      setChords(result.chords);
      if (!tempoHint) requestAnimationFrame(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
      // Load the take into the preview player so it can play along.
      preview.current ??= new Preview(mix);
      await preview.current.loadGuitar(audio);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAnalyzing(false);
    }
  };

  // Re-arrange whenever the chords or band settings change (debounced).
  useEffect(() => {
    if (!analysis || chords.length === 0) return;
    let cancelled = false;
    setArranging(true);
    const id = setTimeout(async () => {
      try {
        const arr = await getArrangement(analysis, chords, band);
        if (!cancelled) setArrangement(arr);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setArranging(false);
      }
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(id);
    };
  }, [analysis, chords, band]);

  // If the band changes mid-preview, restart with the new parts.
  const playingRef = useRef(false);
  playingRef.current = beat !== null;
  useEffect(() => {
    if (playingRef.current && arrangement && analysis) void play(arrangement);
  }, [arrangement]);

  useEffect(() => () => void preview.current?.close(), []);

  const play = async (arr: Arrangement | null = arrangement) => {
    if (!analysis || !arr) return;
    preview.current ??= new Preview(mix);
    await preview.current.play(analysis, arr, (b) => setBeat(b < 0 ? null : b));
    setBeat(-1);
  };

  const changeMix = (track: Track, value: number) => {
    setMix((m) => ({ ...m, [track]: value }));
    preview.current?.setLevel(track, value);
  };

  const download = async (part: Part) => {
    if (!analysis) return;
    setDownloading(part);
    try {
      await downloadMidi(analysis, chords, band, part);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDownloading(null);
    }
  };

  const flats = analysis ? usesFlats(analysis) : false;
  const tuningNote = analysis ? describeTuning(analysis.tuning_cents) : null;

  return (
    <div className="page">
      <header className="masthead">
        <p className="wordmark">RiffBack</p>
        <h1>Play a riff. Get a drummer and a bassist.</h1>
        <p className="lede">
          RiffBack listens to your guitar, works out the tempo, key and chords, and writes a backing track you can
          jam with here or drag into Ableton as MIDI.
        </p>
      </header>

      <main>
        <RecordPanel busy={analyzing} onRecorded={(blob) => void runAnalysis(blob)} onError={setError} />

        {analyzing && (
          <p className="status" role="status">
            Listening for the beat, key and chords…
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        {analysis && (
          <div ref={resultsRef} className="results">
            <section className="readout" aria-label="What RiffBack heard">
              <div className="reading">
                <span className="reading-label">Tempo</span>
                <span className="reading-value">{Math.round(analysis.tempo)}<small> BPM</small></span>
                <span className="reading-fix">
                  Feels wrong?{" "}
                  <button type="button" className="link" disabled={analyzing || !wav}
                    onClick={() => wav && void runAnalysis(wav, analysis.tempo / 2)}>Halve it</button>{" "}
                  or{" "}
                  <button type="button" className="link" disabled={analyzing || !wav}
                    onClick={() => wav && void runAnalysis(wav, analysis.tempo * 2)}>double it</button>
                </span>
              </div>
              <div className="reading">
                <span className="reading-label">Key</span>
                <span className="reading-value">{describeKey(analysis)}</span>
              </div>
              <div className="reading">
                <span className="reading-label">Length</span>
                <span className="reading-value">{analysis.duration.toFixed(1)}<small> s</small></span>
              </div>
            </section>
            {tuningNote && <p className="note">{tuningNote}</p>}

            <ChordChart analysis={analysis} chords={chords} flats={flats} repeats={band.repeats} beat={beat}
              onChange={setChords} />

            <BandPanel band={band} onBand={setBand} mix={mix} onMix={changeMix} playing={beat !== null}
              loading={arranging || !arrangement} onPlay={() => void play()} onStop={stopPreview} />

            <ExportPanel tempo={analysis.tempo} busy={downloading} onDownload={(p) => void download(p)} />
          </div>
        )}
      </main>

      <footer className="footer">
        <p>
          Built with FastAPI, NumPy and SciPy on the server and React and the Web Audio API in the browser. No audio
          is stored.
        </p>
      </footer>
    </div>
  );
}
