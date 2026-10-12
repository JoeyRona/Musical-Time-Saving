import type { Part } from "../api";

interface Props {
  tempo: number;
  busy: Part | null;
  onDownload: (part: Part) => void;
}

const PARTS: { part: Part; label: string }[] = [
  { part: "all", label: "All parts" },
  { part: "drums", label: "Drums" },
  { part: "bass", label: "Bass" },
  { part: "keys", label: "Keys" },
];

export function ExportPanel({ tempo, busy, onDownload }: Props) {
  return (
    <section className="panel" aria-labelledby="export-title">
      <div className="panel-head">
        <h2 id="export-title">Take it into Ableton</h2>
      </div>
      <div className="downloads">
        {PARTS.map(({ part, label }) => (
          <button key={part} type="button" className={part === "all" ? "primary" : "secondary"}
            onClick={() => onDownload(part)} disabled={busy !== null}>
            {busy === part ? "Preparing…" : `Download ${label.toLowerCase()} (.mid)`}
          </button>
        ))}
      </div>
      <ol className="steps">
        <li>Set your Live set's tempo to <strong>{Math.round(tempo)} BPM</strong> (the file carries the exact tempo too).</li>
        <li>Drag the .mid file onto an empty MIDI track, starting at bar 1.</li>
        <li>Load an instrument on each track: a Drum Rack for drums, any bass or keys preset for the others.</li>
        <li>Record your guitar on an audio track over the top.</li>
      </ol>
    </section>
  );
}
