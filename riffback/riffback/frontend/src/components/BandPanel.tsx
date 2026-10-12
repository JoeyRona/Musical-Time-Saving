import { BASS_STYLES, type BandSettings, type BassStyle, DRUM_STYLES, type DrumStyle } from "../api";
import type { Mix, Track } from "../audio/preview";

const DRUM_LABELS: Record<DrumStyle, string> = {
  rock: "Rock",
  halftime: "Half-time",
  ballad: "Ballad",
  "four-on-floor": "Four on the floor",
};

const BASS_LABELS: Record<BassStyle, string> = {
  roots: "Roots",
  eighths: "Driving eighths",
  "root-fifth": "Root and fifth",
  walking: "Walking",
};

const TRACK_LABELS: Record<Track, string> = { guitar: "Your guitar", drums: "Drums", bass: "Bass", keys: "Keys" };

interface Props {
  band: BandSettings;
  onBand: (band: BandSettings) => void;
  mix: Mix;
  onMix: (track: Track, value: number) => void;
  playing: boolean;
  loading: boolean;
  onPlay: () => void;
  onStop: () => void;
}

function Segmented<T extends string>({ legend, name, options, labels, value, onChange }: {
  legend: string;
  name: string;
  options: readonly T[];
  labels: Record<T, string>;
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <fieldset className="segmented">
      <legend>{legend}</legend>
      <div className="segments">
        {options.map((o) => (
          <label key={o} className={o === value ? "segment checked" : "segment"}>
            <input type="radio" name={name} value={o} checked={o === value} onChange={() => onChange(o)} />
            {labels[o]}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function BandPanel({ band, onBand, mix, onMix, playing, loading, onPlay, onStop }: Props) {
  return (
    <section className="panel" aria-labelledby="band-title">
      <div className="panel-head">
        <h2 id="band-title">Pick a band</h2>
      </div>

      <Segmented legend="Drums" name="drums" options={DRUM_STYLES} labels={DRUM_LABELS} value={band.drum_style}
        onChange={(drum_style) => onBand({ ...band, drum_style })} />
      <Segmented legend="Bass" name="bass" options={BASS_STYLES} labels={BASS_LABELS} value={band.bass_style}
        onChange={(bass_style) => onBand({ ...band, bass_style })} />

      <div className="transport">
        <button type="button" className="play-button" onClick={playing ? onStop : onPlay} disabled={loading && !playing}>
          {playing ? "Stop" : loading ? "Arranging…" : "Play with the band"}
        </button>
        <label className="field repeats">
          <span>Times through</span>
          <input type="number" min={1} max={16} value={band.repeats}
            onChange={(e) => onBand({ ...band, repeats: Math.max(1, Math.min(16, Number(e.target.value) || 1)) })} />
        </label>
      </div>

      <div className="mixer" role="group" aria-label="Preview mix">
        {(Object.keys(mix) as Track[]).map((t) => (
          <label key={t} className="fader">
            <span>{TRACK_LABELS[t]}</span>
            <input type="range" min={0} max={1} step={0.01} value={mix[t]} onChange={(e) => onMix(t, Number(e.target.value))} />
          </label>
        ))}
      </div>
    </section>
  );
}
