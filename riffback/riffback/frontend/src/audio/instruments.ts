// Tiny Web Audio synths so the backing track can be previewed in the browser
// without loading any samples. The MIDI download is what you'd use for real.

const midiToHz = (n: number) => 440 * Math.pow(2, (n - 69) / 12);

const noiseCache = new WeakMap<BaseAudioContext, AudioBuffer>();

function noise(ctx: BaseAudioContext): AudioBuffer {
  let buf = noiseCache.get(ctx);
  if (!buf) {
    buf = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
    noiseCache.set(ctx, buf);
  }
  return buf;
}

function envelope(ctx: BaseAudioContext, out: AudioNode, t: number, peak: number, decay: number): GainNode {
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(Math.max(peak, 0.0002), t + 0.004);
  g.gain.exponentialRampToValueAtTime(0.0001, t + decay);
  g.connect(out);
  return g;
}

function noiseHit(ctx: BaseAudioContext, out: AudioNode, t: number, vel: number, decay: number,
  type: BiquadFilterType, freq: number, q = 0.7) {
  const src = ctx.createBufferSource();
  src.buffer = noise(ctx);
  const filter = ctx.createBiquadFilter();
  filter.type = type;
  filter.frequency.value = freq;
  filter.Q.value = q;
  src.connect(filter).connect(envelope(ctx, out, t, vel, decay));
  src.start(t);
  src.stop(t + decay + 0.05);
}

function tone(ctx: BaseAudioContext, out: AudioNode, t: number, type: OscillatorType,
  freqStart: number, freqEnd: number, vel: number, decay: number) {
  const osc = ctx.createOscillator();
  osc.type = type;
  osc.frequency.setValueAtTime(freqStart, t);
  osc.frequency.exponentialRampToValueAtTime(freqEnd, t + decay * 0.6);
  osc.connect(envelope(ctx, out, t, vel, decay));
  osc.start(t);
  osc.stop(t + decay + 0.05);
}

/** General MIDI drum numbers -> synthesised hits. */
export function playDrum(ctx: BaseAudioContext, out: AudioNode, pitch: number, t: number, velocity: number) {
  const v = velocity / 127;
  switch (pitch) {
    case 36: // kick
      tone(ctx, out, t, "sine", 140, 45, v * 1.0, 0.35);
      break;
    case 37: // side stick
      noiseHit(ctx, out, t, v * 0.5, 0.05, "bandpass", 1800, 3);
      tone(ctx, out, t, "triangle", 900, 700, v * 0.25, 0.04);
      break;
    case 38: // snare
      noiseHit(ctx, out, t, v * 0.55, 0.18, "highpass", 1200);
      tone(ctx, out, t, "triangle", 220, 160, v * 0.35, 0.1);
      break;
    case 42: // closed hi-hat
      noiseHit(ctx, out, t, v * 0.22, 0.05, "highpass", 7000);
      break;
    case 46: // open hi-hat
      noiseHit(ctx, out, t, v * 0.22, 0.3, "highpass", 6500);
      break;
    case 49: // crash
      noiseHit(ctx, out, t, v * 0.3, 1.6, "highpass", 5000);
      break;
    case 51: // ride
      noiseHit(ctx, out, t, v * 0.18, 0.5, "bandpass", 6000, 2);
      tone(ctx, out, t, "square", 2900, 2850, v * 0.03, 0.4);
      break;
  }
}

export function playBass(ctx: BaseAudioContext, out: AudioNode, pitch: number, t: number, dur: number, velocity: number) {
  const osc = ctx.createOscillator();
  osc.type = "sawtooth";
  osc.frequency.value = midiToHz(pitch);
  const filter = ctx.createBiquadFilter();
  filter.type = "lowpass";
  filter.frequency.setValueAtTime(900, t);
  filter.frequency.exponentialRampToValueAtTime(250, t + 0.25);
  const g = ctx.createGain();
  const v = (velocity / 127) * 0.5;
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(v, t + 0.01);
  g.gain.setTargetAtTime(v * 0.6, t + 0.05, 0.2);
  g.gain.setTargetAtTime(0.0001, t + dur, 0.03);
  osc.connect(filter).connect(g).connect(out);
  osc.start(t);
  osc.stop(t + dur + 0.2);
}

export function playKeys(ctx: BaseAudioContext, out: AudioNode, pitch: number, t: number, dur: number, velocity: number) {
  const v = (velocity / 127) * 0.09;
  for (const [type, detune, level] of [["triangle", 0, 1], ["sine", 1200, 0.3]] as const) {
    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.value = midiToHz(pitch);
    osc.detune.value = detune;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(v * level, t + 0.02);
    g.gain.setTargetAtTime(v * level * 0.5, t + 0.1, 0.6);
    g.gain.setTargetAtTime(0.0001, t + dur, 0.08);
    osc.connect(g).connect(out);
    osc.start(t);
    osc.stop(t + dur + 0.5);
  }
}
