// Records raw, unprocessed audio from an input (e.g. a Focusrite interface).
//
// MediaRecorder would give compressed WebM/Opus, which the backend can't read
// without extra tools, so an AudioWorklet captures the raw samples instead
// and we encode them as WAV ourselves.

import { encodeWav, pickGuitarChannel } from "./wav";

const WORKLET = `
class CaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (input && input.length) {
      let peak = 0;
      const copy = input.map((ch) => {
        for (let i = 0; i < ch.length; i++) peak = Math.max(peak, Math.abs(ch[i]));
        return ch.slice();
      });
      this.port.postMessage({ channels: copy, peak });
    }
    return true;
  }
}
registerProcessor("capture-processor", CaptureProcessor);
`;

export interface InputDevice {
  deviceId: string;
  label: string;
}

export async function listInputs(): Promise<InputDevice[]> {
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices
    .filter((d) => d.kind === "audioinput")
    .map((d, i) => ({ deviceId: d.deviceId, label: d.label || `Input ${i + 1}` }));
}

export class Recorder {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  private chunks: Float32Array[][] = [];

  /** Called ~40 times a second with the input's peak level (0-1). */
  onLevel: (peak: number) => void = () => {};

  async start(deviceId?: string): Promise<void> {
    this.chunks = [];
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        deviceId: deviceId ? { exact: deviceId } : undefined,
        // Browser "voice call" processing ruins instrument recordings.
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
        channelCount: { ideal: 2 },
      },
    });
    this.ctx = new AudioContext();
    const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
    await this.ctx.audioWorklet.addModule(url);
    URL.revokeObjectURL(url);

    const source = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, "capture-processor");
    let lastLevel = 0;
    this.node.port.onmessage = (e: MessageEvent<{ channels: Float32Array[]; peak: number }>) => {
      this.chunks.push(e.data.channels);
      const now = performance.now();
      if (now - lastLevel > 25) {
        lastLevel = now;
        this.onLevel(e.data.peak);
      }
    };
    // The worklet has to be connected to the output to keep running; a muted
    // gain node stops the guitar being played back through the speakers.
    const mute = this.ctx.createGain();
    mute.gain.value = 0;
    source.connect(this.node).connect(mute).connect(this.ctx.destination);
  }

  get seconds(): number {
    if (!this.ctx) return 0;
    const frames = this.chunks.reduce((n, c) => n + (c[0]?.length ?? 0), 0);
    return frames / this.ctx.sampleRate;
  }

  async stop(): Promise<Blob> {
    const ctx = this.ctx;
    if (!ctx) throw new Error("Not recording");
    const sampleRate = ctx.sampleRate;
    this.node?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    await ctx.close();
    this.ctx = null;

    const numChannels = Math.max(1, ...this.chunks.map((c) => c.length));
    const total = this.chunks.reduce((n, c) => n + (c[0]?.length ?? 0), 0);
    const channels = Array.from({ length: numChannels }, () => new Float32Array(total));
    let offset = 0;
    for (const chunk of this.chunks) {
      const len = chunk[0]?.length ?? 0;
      for (let c = 0; c < numChannels; c++) channels[c].set(chunk[c] ?? chunk[0], offset);
      offset += len;
    }
    this.chunks = [];
    return encodeWav([pickGuitarChannel(channels)], sampleRate);
  }

  cancel(): void {
    this.node?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    void this.ctx?.close();
    this.ctx = null;
    this.chunks = [];
  }
}
