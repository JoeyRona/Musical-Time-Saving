import { describe, expect, it } from "vitest";
import type { ChordEvent } from "./api";
import { allChords, chordName, chordsByBar, replaceChord, usesFlats } from "./music";
import { barStarts, pickupLength } from "./audio/preview";

const chords: ChordEvent[] = [
  { bar: 0, beat: 0, beats: 4, root: 7, quality: "maj", name: "G" },
  { bar: 1, beat: 0, beats: 2, root: 4, quality: "min", name: "Em" },
  { bar: 1, beat: 2, beats: 2, root: 0, quality: "maj", name: "C" },
];

describe("chord names", () => {
  it("spells flat keys with flats", () => {
    expect(usesFlats({ key_tonic: 5, key_mode: "major" })).toBe(true);
    expect(usesFlats({ key_tonic: 7, key_mode: "major" })).toBe(false);
    expect(chordName(10, "maj", true)).toBe("Bb");
    expect(chordName(10, "min", false)).toBe("A#m");
    expect(allChords(false)).toHaveLength(24);
  });

  it("groups chords by bar and replaces one", () => {
    const bars = chordsByBar(chords, 2);
    expect(bars[1].map((c) => c.name)).toEqual(["Em", "C"]);
    const edited = replaceChord(chords, chords[2], 9, "min", false);
    expect(edited[2]).toMatchObject({ root: 9, quality: "min", name: "Am", beat: 2 });
    expect(edited[0]).toBe(chords[0]);
  });
});

describe("preview timing", () => {
  const analysis = {
    tempo: 120,
    beats_per_bar: 4,
    bars: 2,
    first_downbeat: 1.5,
    beat_times: [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
  };

  it("finds where each bar starts in the recording", () => {
    // beats 1.5 and 3.5 start bars 1 and 2; bar 3's start is past the last beat
    expect(barStarts(analysis as never)).toEqual([1.5, 3.5, 5.5]);
  });

  it("measures the pickup before bar 1", () => {
    expect(pickupLength(analysis as never)).toBeCloseTo(0.55);
  });
});
