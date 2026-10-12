import type { Analysis, ChordEvent, Quality } from "./api";

const SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const FLATS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"];
const FLAT_MAJOR = new Set([5, 10, 3, 8, 1]);
const FLAT_MINOR = new Set([2, 7, 0, 5, 10]);

export function usesFlats(analysis: Pick<Analysis, "key_tonic" | "key_mode">): boolean {
  return (analysis.key_mode === "major" ? FLAT_MAJOR : FLAT_MINOR).has(analysis.key_tonic);
}

export function chordName(root: number, quality: Quality, flats: boolean): string {
  return (flats ? FLATS : SHARPS)[root] + (quality === "min" ? "m" : "");
}

/** Every major and minor chord, for the chord picker. */
export function allChords(flats: boolean): { root: number; quality: Quality; name: string }[] {
  const out = [];
  for (const quality of ["maj", "min"] as const) {
    for (let root = 0; root < 12; root++) out.push({ root, quality, name: chordName(root, quality, flats) });
  }
  return out;
}

/** The chords that start in each bar, e.g. bars[2] = [Em (2 beats), C (2 beats)]. */
export function chordsByBar(chords: ChordEvent[], bars: number): ChordEvent[][] {
  const out: ChordEvent[][] = Array.from({ length: bars }, () => []);
  for (const c of chords) if (c.bar < bars) out[c.bar].push(c);
  return out;
}

export function replaceChord(chords: ChordEvent[], target: ChordEvent, root: number, quality: Quality, flats: boolean): ChordEvent[] {
  return chords.map((c) => (c === target ? { ...c, root, quality, name: chordName(root, quality, flats) } : c));
}
