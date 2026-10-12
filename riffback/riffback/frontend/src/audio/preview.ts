// Plays your recorded riff together with the generated band.
//
// You played without a click, so your riff will drift slightly against the
// band's perfectly steady tempo. To keep you in time, the recording is cut
// into bars using the detected beat times and each bar is re-started exactly
// on the band's grid ("bar-by-bar resync"). This keeps your pitch untouched,
// unlike time-stretching.

import type { Analysis, Arrangement } from "../api";
import { playBass, playDrum, playKeys } from "./instruments";

export type Track = "guitar" | "drums" | "bass" | "keys";
export type Mix = Record<Track, number>;

export const DEFAULT_MIX: Mix = { guitar: 0.9, drums: 0.8, bass: 0.8, keys: 0.35 };

/** Positions (in seconds within the recording) where each bar starts. */
export function barStarts(analysis: Analysis): number[] {
  const { beat_times: beats, first_downbeat, bars, beats_per_bar, tempo } = analysis;
  const beatSec = 60 / tempo;
  let first = 0;
  let best = Infinity;
  beats.forEach((t, i) => {
    if (Math.abs(t - first_downbeat) < best) {
      best = Math.abs(t - first_downbeat);
      first = i;
    }
  });
  const starts: number[] = [];
  for (let b = 0; b <= bars; b++) {
    const i = first + b * beats_per_bar;
    starts.push(i < beats.length ? beats[i] : starts[starts.length - 1] + beats_per_bar * beatSec);
  }
  return starts;
}

/** Seconds of playing before bar 1 (a pickup), capped at one bar. */
export function pickupLength(analysis: Analysis): number {
  const firstSound = Math.max(0, (analysis.beat_times[0] ?? 0) - 0.05);
  const lead = analysis.first_downbeat - firstSound;
  const barSec = (analysis.beats_per_bar * 60) / analysis.tempo;
  return lead > 0.1 ? Math.min(lead, barSec) : 0;
}

export class Preview {
  private ctx = new AudioContext();
  private buses: Record<Track, GainNode>;
  private master: GainNode;
  private startTime = 0;
  private raf = 0;
  private guitar: AudioBuffer | null = null;
  playing = false;

  constructor(mix: Mix) {
    this.master = this.ctx.createGain();
    this.master.connect(this.ctx.destination);
    this.buses = {} as Record<Track, GainNode>;
    for (const track of Object.keys(mix) as Track[]) {
      const g = this.ctx.createGain();
      g.gain.value = mix[track];
      g.connect(this.master);
      this.buses[track] = g;
    }
  }

  async loadGuitar(wav: Blob): Promise<void> {
    this.guitar = await this.ctx.decodeAudioData(await wav.arrayBuffer());
  }

  setLevel(track: Track, value: number): void {
    this.buses[track].gain.setTargetAtTime(value, this.ctx.currentTime, 0.02);
  }

  /** Start playback. `onBeat` gets the current beat (float) every frame, or -1 when finished. */
  async play(analysis: Analysis, arrangement: Arrangement, onBeat: (beat: number) => void): Promise<void> {
    this.stop();
    await this.ctx.resume();
    this.master = this.ctx.createGain();
    this.master.connect(this.ctx.destination);
    for (const bus of Object.values(this.buses)) {
      bus.disconnect();
      bus.connect(this.master);
    }

    const beatSec = 60 / arrangement.tempo;
    const lead = this.guitar ? pickupLength(analysis) : 0;
    const t0 = this.ctx.currentTime + 0.2 + lead;
    this.startTime = t0;
    this.playing = true;

    for (const n of arrangement.notes) {
      const t = t0 + n.start * beatSec;
      const dur = n.duration * beatSec;
      if (n.track === "drums") playDrum(this.ctx, this.buses.drums, n.pitch, t, n.velocity);
      else if (n.track === "bass") playBass(this.ctx, this.buses.bass, n.pitch, t, dur, n.velocity);
      else playKeys(this.ctx, this.buses.keys, n.pitch, t, dur, n.velocity);
    }

    if (this.guitar) this.scheduleGuitar(analysis, arrangement, t0, beatSec);

    const endBeat = arrangement.total_beats + 2;
    const tick = () => {
      if (!this.playing) return;
      const beat = (this.ctx.currentTime - this.startTime) / beatSec;
      if (beat > endBeat) {
        this.playing = false;
        onBeat(-1);
        return;
      }
      onBeat(beat);
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  private scheduleGuitar(analysis: Analysis, arrangement: Arrangement, t0: number, beatSec: number) {
    const guitar = this.guitar!;
    const starts = barStarts(analysis);
    const barSec = analysis.beats_per_bar * beatSec;
    const loops = Math.round(arrangement.total_beats / (analysis.bars * analysis.beats_per_bar));
    const fade = 0.012;

    // Notes picked before bar 1 (a pickup) play once, leading into the band.
    const lead = pickupLength(analysis);
    if (lead > 0) this.playSlice(guitar, starts[0] - lead, lead + fade, t0 - lead, fade);
    for (let loop = 0; loop < loops; loop++) {
      for (let bar = 0; bar < analysis.bars; bar++) {
        const from = starts[bar];
        if (from >= guitar.duration) break;
        // Let the last bar ring out; otherwise stop just after the next bar line.
        const isLast = loop === loops - 1 && bar === analysis.bars - 1;
        const length = isLast ? guitar.duration - from : Math.min(starts[bar + 1] - from, barSec) + fade;
        const when = t0 + (loop * analysis.bars + bar) * barSec;
        this.playSlice(guitar, from, length, when, fade);
      }
    }
  }

  private playSlice(buffer: AudioBuffer, offset: number, length: number, when: number, fade: number) {
    if (length <= 0) return;
    const src = this.ctx.createBufferSource();
    src.buffer = buffer;
    const g = this.ctx.createGain();
    g.gain.setValueAtTime(0, Math.max(when, 0));
    g.gain.linearRampToValueAtTime(1, when + fade);
    g.gain.setValueAtTime(1, when + length - fade);
    g.gain.linearRampToValueAtTime(0, when + length);
    src.connect(g).connect(this.buses.guitar);
    if (when < this.ctx.currentTime) {
      // Can't start in the past: skip into the slice instead.
      const late = this.ctx.currentTime - when;
      src.start(this.ctx.currentTime, offset + late, Math.max(0, length - late));
    } else {
      src.start(when, offset, length);
    }
  }

  stop(): void {
    this.playing = false;
    cancelAnimationFrame(this.raf);
    // Disconnecting the master silences everything already scheduled.
    this.master.disconnect();
  }

  async close(): Promise<void> {
    this.stop();
    await this.ctx.close();
  }
}
