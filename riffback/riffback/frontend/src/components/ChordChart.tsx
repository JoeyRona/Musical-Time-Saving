import type { Analysis, ChordEvent, Quality } from "../api";
import { allChords, chordsByBar, replaceChord } from "../music";

interface Props {
  analysis: Analysis;
  chords: ChordEvent[];
  flats: boolean;
  repeats: number;
  beat: number | null; // playhead position in beats, null when stopped
  onChange: (chords: ChordEvent[]) => void;
}

const BARS_PER_LINE = 4;

/** A lead sheet: chord symbols over slash notation, four bars to a line. */
export function ChordChart({ analysis, chords, flats, repeats, beat, onChange }: Props) {
  const { bars, beats_per_bar: bpb } = analysis;
  const byBar = chordsByBar(chords, bars);
  const options = allChords(flats);

  const loopBeats = bars * bpb;
  const playing = beat !== null && beat >= 0 && beat < loopBeats * repeats;
  const loopBeat = playing ? beat % loopBeats : -1;
  const currentBar = playing ? Math.floor(loopBeat / bpb) : -1;
  const currentBeat = playing ? Math.floor(loopBeat % bpb) : -1;
  const currentPass = playing ? Math.floor(beat / loopBeats) + 1 : 0;

  const lines: number[][] = [];
  for (let b = 0; b < bars; b += BARS_PER_LINE) {
    lines.push(Array.from({ length: Math.min(BARS_PER_LINE, bars - b) }, (_, i) => b + i));
  }

  return (
    <figure className="chart" aria-label="Chord chart">
      <figcaption className="chart-caption">
        <span>Your riff</span>
        <span className="chart-meta">
          {bars} {bars === 1 ? "bar" : "bars"} of {bpb}/4{repeats > 1 && `, played ${repeats} times`}
          {playing && repeats > 1 && <span className="pass"> (pass {currentPass})</span>}
        </span>
      </figcaption>

      {lines.map((line, li) => (
        <div className="staff" key={li}>
          {line.map((bar) => (
            <div
              key={bar}
              className={[
                "bar",
                bar === 0 ? "repeat-start" : "",
                bar === bars - 1 && repeats > 1 ? "repeat-end" : "",
                bar === bars - 1 && repeats === 1 ? "final" : "",
                bar === currentBar ? "is-current" : "",
              ].join(" ")}
              style={{ gridTemplateColumns: `repeat(${bpb}, 1fr)` }}
            >
              <span className="bar-number" aria-hidden="true">{bar + 1}</span>
              {byBar[bar].map((ev) => (
                <label key={`${ev.bar}-${ev.beat}`} className="chord" style={{ gridColumn: `${ev.beat + 1} / span ${Math.min(ev.beats, bpb - ev.beat)}` }}>
                  <span className="sr-only">Bar {bar + 1}, beat {ev.beat + 1} chord</span>
                  <select
                    value={`${ev.root}-${ev.quality}`}
                    onChange={(e) => {
                      const [root, quality] = e.target.value.split("-");
                      onChange(replaceChord(chords, ev, Number(root), quality as Quality, flats));
                    }}
                  >
                    {options.map((o) => (
                      <option key={o.name} value={`${o.root}-${o.quality}`}>{o.name}</option>
                    ))}
                  </select>
                </label>
              ))}
              <div className="slashes" aria-hidden="true" style={{ gridTemplateColumns: `repeat(${bpb}, 1fr)` }}>
                {Array.from({ length: bpb }, (_, i) => (
                  <span key={i} className={bar === currentBar && i === currentBeat ? "slash lit" : "slash"}>/</span>
                ))}
              </div>
              {bar === bars - 1 && repeats > 1 && <span className="times" aria-hidden="true">×{repeats}</span>}
            </div>
          ))}
        </div>
      ))}
      <p className="hint chart-hint">Got a chord wrong? Click it to change it. The band follows your edits.</p>
    </figure>
  );
}
